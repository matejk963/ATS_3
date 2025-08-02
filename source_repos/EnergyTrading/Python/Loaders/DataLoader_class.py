# -*- coding: utf-8 -*-
"""
Created on Thu Nov  2 14:48:49 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
from pandas.tseries.offsets import Day, Week
from sqlalchemy import create_engine, text
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import json
import os

# from Loaders import RLD_fetch as RF
from Database.DB_reader import Database as DB
from Loaders.EikonFut_class import EikonFut as EF

from Loaders.AvCapFetch_rel_class import AvCapFetch as ACF


class DataLoader():
    """DOCUMENTATION
    Class to gather and process input and output data for modeling,
    analysing and trading puposes.

    Attributes

    ----------

    start_date : datetime.datetime/date string
            Start of the time series the DataLoader is supposed to gather,
        process and compile data for in a fashion defined by each individual methods.
            This paramters is passed defaultly to each method
        that requires time frame definition.

    end_date : datetime.datetime/date string
            End of the time series the DataLoader is supposed to gather,
        process and compile data for in a fashion defined by each individual methods.
            This paramters is passed defaultly to each method
        that requires time frame definition.

    predictors_dict : dict
            A dictionary containing configuration data for desired
        predictors data structures

        Dict structure:
            {
                'df_name': {                            #str: The name of the predictor dataframe
                    'method': {                        #str: The name of method used for creating df
                        'param_1_name': param_1_value,  #A dictionary of paramters that enter the methods
                        'param_2_name': param_2_value
                    }
                }
            }

    targets_dict : dict
            A dictionary containing configuration data for desired
        target data structures

        Dict structure:
            {
                'target_name': {                            #str: The name of the target dataframe
                    'method': {                             #str: The name of method used for creating df
                        'param_1_name': param_1_value,      #A dictionary of paramters that enter the methods
                        'param_2_name': param_2_value
                    }
                }
            }


    Methods
    -------

    __init__(self, start_date, end_date,
             predictors_dict, targets_dict)
            Initializes DataLoader with star/end of desired timeframe,
        predictors_dict and targets_dict to specify the desired data structures

    get_RLD_raw_fcst(self, country='de', ec_type=0,
                    sD_fcst=None, eD_fcst=None):
            Method to fetch FORECASTED data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) the full
        EC forecast is fetched from database.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__

    get_RLD_raw_normal(self, country='de', ec_type=0,
                    sD_fcst=None, eD_fcst=None):
            Method to fetch NORMAL data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) next 15 days
        worth of normals are fetched to match the EC forecast horizon.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__

    get_RLD_matrix_creator(self,data_type,
                               fcst_window='wa',country='de',
                               ec_type=0, sD_fcst=None, eD_fcst=None)
            Method that transforms the df from get_RLD_raw_fcst/get_RLD_raw_normal to
        matrix with shape (n,m) where
        n = len(date_range(start_date,end_date,daily))
        m = no. of hours in forecast window('wa' = week ahead forecast => 168 hours,
                                             ---starting nearest next Monday---,
                                            'wknd' = weekend ahead fcst => 48 hours,
                                            ---starting nearest next Saturday---,
                                            'da' = day ahead fcst => 24 hours,
                                            ---next day---)
        data_type : str, specifies weather to fetch forecasted data or normal data
        ec_type : int, specifies the type of EC forecast (0,6,12,18)
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__

    get_RLD_fcst(self, df_name,
                    ec_type=0, sD_fcst=None, eD_fcst=None)
            Calling function for forecast ,'fcst', data_type self.get_RLD_matrix_creator

    get_RLD_normal(self, df_name,
                    ec_type=0, sD_fcst=None, eD_fcst=None)
            Calling function for normal ,'normal', data_type self.get_RLD_matrix_creator

    Example
    -------

    >>> start_date = datetime.datetime(2023,1,1)
    >>> end_date = datetime.datetime(2023,2,1)
    >>> predictors_dict = {
        'wa_rld_fcst': {
            'get_RLD_fcst':{
                'fcst_dim': 'da'}}}
    >>> targets_dict = {
        'target_df': {
            'target_method': {
                'target_param1_name': 'target_param1_name'}}}


    """

    def __init__(self, start_date, end_date, predictors_dict, targets_dict,
                 _db_config_path=None):
        self._sD = pd.to_datetime(start_date)
        self._eD = pd.to_datetime(end_date)
        self._sD_str=start_date
        self._eD_str=end_date
        self._pred_dict = predictors_dict
        self._targ_dict = targets_dict


        if _db_config_path:
            self._db = DB(path_name=_db_config_path)
        else:
            self._db = DB()

    @property
    def start_date(self):
        return self._sD

    @property
    def end_date(self):
        return self._eD

    @property
    def predictors_dict(self):
        return self._pred_dict

    @property
    def targets_dict(self):
        return self._targ_dict
    
    def get_raw_RLD_from_local(self, country='de', ec_type=0,
                               sD_fcst=None, eD_fcst=None,
                               just_rld=True):
        """

        Parameters
        ----------
        country : TYPE, str
            DESCRIPTION. The default is 'de'.
        ec_type : TYPE, int
            DESCRIPTION. The default is 0.
        sD_fcst : TYPE, datetime
            DESCRIPTION. The default is None.
        eD_fcst : TYPE, datetime
            DESCRIPTION. The default is None.

        Returns
        -------
        None.

        """
        
        
        
        

    def get_RLD_raw_fcst(self, country='de', ec_type=0,
                         sD_fcst=None, eD_fcst=None):
        """
        Raw residual forecast data fetch
            Method to fetch FORECASTED data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) the full
        EC forecast is fetched from database.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__
        """

        db_obj = self._db
        con = db_obj.connection_string
        engine = create_engine(con)
        schema = 'residual'

        if sD_fcst is None:
            sD_fcst = self._sD
        if eD_fcst is None:
            eD_fcst = self._eD

        # Ensure sD_fcst and eD_fcst are not None and are properly formatted dates (as strings)
        if sD_fcst is None or eD_fcst is None:
            raise ValueError("Start date and end date must be provided.")

        # Query the database for column names containing 'date' or 'ens'
        column_query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND (column_name LIKE '%%date%%' OR column_name LIKE '%%ens%%')
        """
        # Execute the query passing the parameters as a tuple
        # column_result = engine.execute(column_query, (schema, country))
        with engine.connect() as connection:
            column_result = connection.execute(column_query, {'schema': schema, 'country': country})
        columns = [row['column_name'] for row in column_result]

        if columns:
            placeholders = ', '.join(columns)
            main_query = f"""
            SELECT {placeholders}
            FROM {schema}.{country}
            WHERE DATE(forecast_date) BETWEEN %s AND %s
              AND EXTRACT(HOUR FROM forecast_date) = 0
            """
            # Execute the main query passing the date parameters as a tuple
            raw_data = pd.read_sql(main_query, con=engine, params=(sD_fcst, eD_fcst))
            return raw_data
        else:
            raise ValueError("No columns found with 'date' or 'ens' in their names.")

    def get_RLD_raw_normal(self, country='de', sD_fcst=None, eD_fcst=None):
        """
        Raw Residual normals data fetch
            Method to fetch NORMAL data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) next 15 days
        worth of normals are fetched to match the EC forecast horizon.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__
        """

        con = self._db.connection_string
        engine = create_engine(con)
        schema = 'normals'  # Adjust the schema as per your database structure

        # Use default dates if none provided
        sD_fcst = self._sD if sD_fcst is None else sD_fcst
        eD_fcst = self._eD if eD_fcst is None else eD_fcst

        # Create a date range from sD_fcst to eD_fcst
        date_range = pd.date_range(start=sD_fcst, end=eD_fcst)

        # Ensure sD_fcst and eD_fcst are not None
        if sD_fcst is None or eD_fcst is None:
            raise ValueError("Start date and end date must be provided.")

        # Use the correct column name for datetime
        datetime_column = 'value_date'

        # SQL query to select all data between the specified dates
        main_query = f"""
        SELECT *
        FROM {schema}.{country}
        WHERE DATE({datetime_column}) BETWEEN %s AND %s
        """
        # Querying data from sD_fcst to eD_fcst + 15 days
        raw_data = pd.read_sql(main_query, con=engine, params=(sD_fcst, eD_fcst + timedelta(days=15)))

        # Initialize an empty DataFrame for the combined data
        combined_data = pd.DataFrame()

        # Process the raw_data for each date in date_range
        for date in date_range:
            # Filter data for 15 days starting from 'date'
            filtered_data = raw_data[(pd.to_datetime(raw_data[datetime_column]) >= date) & (
                    pd.to_datetime(raw_data[datetime_column]) < date + timedelta(days=15))].copy()

            # Add the forecast_date column with only the date from the date range
            filtered_data['forecast_date'] = date

            # Combine the data
            combined_data = pd.concat([combined_data, filtered_data], ignore_index=True)

        return combined_data

    def get_RLD_matrix_creator(self, data_type,
                               fcst_window='wa', country='de',
                               ec_type=0, sD_fcst=None, eD_fcst=None):
        """
        Creating data matrix

            Method that transforms the df from get_RLD_raw_fcst/get_RLD_raw_normal to
        matrix with shape (n,m) where
        n = len(date_range(start_date,end_date,daily))
        m = no. of hours in forecast window('wa' = week ahead forecast => 168 hours,
                                             ---starting nearest next Monday---,
                                            'wknd' = weekend ahead fcst => 48 hours,
                                            ---starting nearest next Saturday---,
                                            'da' = day ahead fcst => 24 hours,
                                            ---next day---)
        data_type : str, specifies weather to fetch forecasted data or normal data
        ec_type : int, specifies the type of EC forecast (0,6,12,18)
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__
        """

        assert fcst_window in ['wa', 'wknd', 'da'], "Forecast window must be one of ['wa', 'wknd', 'da']"

        if sD_fcst is None:
            sD_fcst = self._sD
        if eD_fcst is None:
            eD_fcst = self._eD

        if data_type in ['fcst']:

            # Fetch the historical RLD data for the given time frame and ec_type
            try:
                df = self.get_RLD_raw_fcst(country)
            except Exception as e:
                raise Exception(f"Error fetching historical RLD data: {e}")

            df.sort_values(['forecast_date', 'value_date'],
                           inplace=True)
            df['forecast_date'] = pd.to_datetime(df['forecast_date'])
            df['value_date'] = pd.to_datetime(df['value_date'])
            df['rld'] = df['con_ens'] - df['wind_ens'] - df['solar_ens']
            df = df.drop(columns=['con_ens', 'wind_ens', 'solar_ens'])
            df.sort_values(['forecast_date', 'value_date'], inplace=True)

        elif data_type in ['normal']:
            # Fetch the historical RLD data for the given time frame and ec_type
            try:
                df = self.get_RLD_raw_normal(country)
            except Exception as e:
                raise Exception(f"Error fetching historical RLD data: {e}")

            df.sort_values(['forecast_date', 'value_date'],
                           inplace=True)
            df['forecast_date'] = pd.to_datetime(df['forecast_date'])
            df['value_date'] = pd.to_datetime(df['value_date'])
            df['rld'] = df['con'] - df['wind'] - df['solar']
            df = df.drop(columns=['con', 'wind', 'solar'])
            df.sort_values(['forecast_date', 'value_date'], inplace=True)

        # Define function to get the pivot table based on forecast window
        def get_pivot_table(df, index_col, pivot_col, value_col, periods, aggfunc='mean'):
            try:
                pivot = df.pivot(index=index_col, columns=pivot_col, values=value_col, aggfunc=aggfunc).fillna(0)
                pivot = pivot.loc[:, pivot.columns.isin(range(periods))]
                return pivot.copy()
            except Exception as e:
                raise Exception(f"Error creating pivot table: {e}")

        if fcst_window == 'wa':  # Week Ahead
            df['hour_of_week'] = ((df['value_date'] - df['forecast_date'].apply(lambda x: x + pd.Timedelta(
                days=(7 if x.weekday() == 0 else 7 - x.weekday())))).dt.total_seconds() // 3600).astype(int)
            df_out = get_pivot_table(df, 'forecast_date', 'hour_of_week', 'rld', 168)

        elif fcst_window == 'wknd':  # Weekend Ahead
            df['weekday'] = df['forecast_date'].dt.weekday
            df['next_saturday'] = df['forecast_date'] + pd.to_timedelta(((12 - df['weekday']) % 7), unit='d')
            df['hour_of_weekend'] = ((df['value_date'] - df['next_saturday']).dt.total_seconds() // 3600).astype(int)
            df_out = get_pivot_table(df, 'forecast_date', 'hour_of_weekend', 'rld', 48)

        elif fcst_window == 'da':  # Day Ahead
            df['next_day'] = df['forecast_date'] + pd.Timedelta(days=1)
            df['hour_of_day_ahead'] = ((df['value_date'] - df['next_day']).dt.total_seconds() // 3600).astype(int)
            df_out = get_pivot_table(df, 'forecast_date', 'hour_of_day_ahead', 'rld', 24)

        # Format the MultiIndex
        df_out.columns = pd.MultiIndex.from_product([['rld'], df_out.columns], names=['variable', 'hour'])

        # Flatten the MultiIndex for df_out
        if data_type in ['fcst']:
            df_out.columns = ['rld_fcst_' + fcst_window + '_' + str(hour) + 'h' for hour in
                              df_out.columns.get_level_values(1)]
        if data_type in ['normal']:
            df_out.columns = ['rld_norm_' + fcst_window + '_' + str(hour) + 'h' for hour in
                              df_out.columns.get_level_values(1)]

        return df_out
        # return raw_rld

    def get_RLD_fcst(self, fcst_window='wa', country='de',
                     ec_type=0, sD_fcst=None, eD_fcst=None):
        """
        Residuals forecast final matrix

        Calling function for forecast ,'fcst', data_type self.get_RLD_matrix_creator
        """
        return self.get_RLD_matrix_creator(data_type='fcst',
                                           fcst_window=fcst_window,
                                           country=country,
                                           sD_fcst=None, eD_fcst=None)

    def get_RLD_normal(self, fcst_window='wa', country='de',
                       sD_fcst=None, eD_fcst=None):
        """
        Residuals normals final matrix

        Calling function for normal ,'normal', data_type self.get_RLD_matrix_creator
        """
        return self.get_RLD_matrix_creator(data_type='normal',
                                           fcst_window=fcst_window,
                                           country=country,
                                           sD_fcst=None, eD_fcst=None)

    #####################################
    # Following methods implement gas, coal and eua arrays + their most used combinations

    @staticmethod
    def is_less_than_5_days_to_month_end(date):

        given_date = date

        # Calculate the last day of the given date's month
        next_month = given_date.replace(day=28) + dt.timedelta(days=4)
        last_day_of_month = next_month - dt.timedelta(days=next_month.day)

        # Check if the difference between the last day of the month and the given date is less than 5 days
        return (last_day_of_month - given_date).days < 5

    @staticmethod
    def is_less_than_12_days_to_year_end(date):

        given_date = date

        # Calculate the last day of the given date's month
        next_year = given_date.replace(day=28).replace(month=12) + dt.timedelta(days=4)
        last_day_of_year = next_year - dt.timedelta(days=next_year.day)

        # Check if the difference between the last day of the month and the given date is less than 5 days
        return (last_day_of_year - given_date).days < 12

    @staticmethod
    def extract_year_month_day(date_str):
        """
        Extracts and returns the year, month, and day from a given date string.

        Args:
        date_str (str): The date string in the format 'YYYY-MM-DD'.

        Returns:
        tuple: A tuple containing the year, month, and day as integers.
        """
        # Parse the date string into a datetime object
        date_obj = dt.datetime.strptime(date_str, '%Y-%m-%d')

        # Extract year, month, and day
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day

        return year, month, day

    def get_gas_coal_eua_arr(self, market, tenor, moving_window=7, sD_fcst=None, eD_fcst=None):
        """
        Retrieves and processes gas/coal/eua market data.

        This method fetches gas/coal/eua market data for a specified date range and computes
        forward prices while adjusting for a moving window period.

        Args:
            market (str): Must be in ['gas', 'coal', 'eua'].
            tenor (str): Must be in ['M', 'Y'].
            moving_window (int): The size of the moving window in days for calculating prices.
            sD_fcst (str): The start date of the forecast period in 'YYYY-MM-DD' format.
            eD_fcst (str): The end date of the forecast period in 'YYYY-MM-DD' format.

        Returns:
            pandas.DataFrame: A DataFrame containing the processed gas/coal/eua market data.
        """

        # Initial transformations and assertions

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str

        assert market in ['gas', 'coal', 'eua'], "Error: market parameter must be noe of ['gas', 'coal', 'eua']!"
        assert tenor in ['M', 'Y'], "Error: tenor parameter must be noe of ['M', 'Y']!"

        # Initialize an object to fetch gas/coal/eua market data
        obj = EF(market)

        # Convert the forecast start and end dates into datetime objects
        sD = self.extract_year_month_day(sD_fcst)
        eD = self.extract_year_month_day(eD_fcst)

        # Adjust the start date backward by twice the moving window days
        sD = dt.datetime(sD[0], sD[1], sD[2]) - relativedelta(days=moving_window * 2)
        eD = dt.datetime(eD[0], eD[1], eD[2])

        # Define lists for product and delivery types; used in data fetching
        product_list = [tenor + '_1', tenor + '_2']
        delivery_list = ['base', 'base']
        year_list = [None, None]

        # Fetch market data using predefined lists
        df = obj.fwd_cont_df(sD, eD, product_list, delivery_list, year_list).reset_index()

        # Calculate forward prices based on proximity to month-end or year-end
        if tenor == 'M':
            df['fwd_price_' + df.columns[1].replace('_', '') + '_dateminus0'] = (
                    df[df.columns[1]] * df[df.columns[0]].apply(
                lambda x: not self.is_less_than_5_days_to_month_end(x)) +
                    df[df.columns[2]] * df[df.columns[0]].apply(lambda x: self.is_less_than_5_days_to_month_end(x))
            )
        elif tenor == 'Y':
            df['fwd_price_' + df.columns[1].replace('_', '') + '_dateminus0'] = (
                    df[df.columns[1]] * df[df.columns[0]].apply(lambda x: not self.is_less_than_12_days_to_year_end(x)) +
                    df[df.columns[2]] * df[df.columns[0]].apply(lambda x: self.is_less_than_12_days_to_year_end(x))
            )

        # Create additional columns for each day in the moving window
        # These columns represent shifted forward prices
        for i in range(moving_window - 1):
            col_name = 'fwd_price_' + df.columns[1].replace('_', '') + '_dateminus' + str(i + 1)
            df[col_name] = df['fwd_price_' + df.columns[1].replace('_', '') + '_dateminus0'].shift(i + 1)

        # Drop the original second and third columns used to compute forward prices
        df.drop(df.columns[[1, 2]], axis=1, inplace=True)

        # Filter the DataFrame to only include rows within the specified forecast date range
        df_out = df[(df['Date'] >= sD_fcst) & (df['Date'] <= eD_fcst)].reset_index(drop=True)

        # Return the filtered DataFrame
        return df_out

    def get_coal_avg_M1_fwd_price_prev_month_arr(self, moving_window=7, sD_fcst=None, eD_fcst=None):
        """
        Retrieves and processes average M1 (month ahead) coal forward prices for the previous month of the given date.

        This method fetches coal market data for a specified date range and computes
        average M1 (month ahead) coal forward prices for the previous month of the given date while adjusting for a moving window period.

        Args:
            moving_window (int): The size of the moving window in days for calculating prices.
            sD_fcst (str): The start date of the forecast period in 'YYYY-MM-DD' format.
            eD_fcst (str): The end date of the forecast period in 'YYYY-MM-DD' format.

        Returns:
            pandas.DataFrame: A DataFrame containing the processed coal market data.
        """

        # Initial transformations and assertions

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str

        # Call the forward prices raw data with already existing general method
        df = self.get_gas_coal_eua_arr('coal', 'M', 1, (dt.datetime.strptime(sD_fcst, '%Y-%m-%d')- relativedelta(days=62)).strftime('%Y-%m-%d'), eD_fcst) # ensuring long enough history is taken
        df['Current_Month'] = pd.to_datetime(df['Date']).dt.strftime('%Y%m')
        df['Previous_Month'] = pd.to_datetime(df['Date']).apply(lambda x: x - relativedelta(months=1)).dt.strftime(
            '%Y%m')

        #Create monthly average for M1 coal fwd prices
        mthly_avgs = pd.DataFrame(
            df['fwd_price_coalM1_dateminus0'].groupby(df['Current_Month']).mean()).reset_index().rename(
            columns={'Current_Month': 'Month', 'fwd_price_coalM1_dateminus0': 'coal_avg_M1_fwd_price'})

        #
        df=df.merge(mthly_avgs, left_on='Previous_Month', right_on='Month', how='left')[
            ['Date', 'coal_avg_M1_fwd_price']].rename(
            columns={'coal_avg_M1_fwd_price': 'coal_avg_M1_fwd_price_prev_month_dateminus0'})



        # Create additional columns for each day in the moving window
        # These columns represent shifted forward prices
        for i in range(moving_window - 1):
            col_name = 'coal_avg_M1_fwd_price_prev_month' + '_dateminus' + str(i + 1)
            df[col_name] = df['coal_avg_M1_fwd_price_prev_month_dateminus0'].shift(i + 1)

        # Filter the DataFrame to only include rows within the specified forecast date range
        df_out = df[(df['Date'] >= sD_fcst) & (df['Date'] <= eD_fcst)].reset_index(drop=True)

        # Return the filtered DataFrame
        return df_out

    def get_gas_mc_arr(self, moving_window=7, sD_fcst=None, eD_fcst=None):
        """
         Combines the already created partial function to give an estimate of marginal cost of gas
         for the given date while adjusting for a moving window period. The current formula used
         is gas_mc=gas+eua*0.2

        Args:
            moving_window (int): The size of the moving window in days for calculating prices.
            sD_fcst (str): The start date of the forecast period in 'YYYY-MM-DD' format.
            eD_fcst (str): The end date of the forecast period in 'YYYY-MM-DD' format.

        Returns:
            pandas.DataFrame: A DataFrame containing the processed market data.
        """

        # Initial transformations and assertions

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str

        #calculating partial costs
        gas_arr = self.get_gas_coal_eua_arr('gas', 'M', moving_window, sD_fcst, eD_fcst)
        eua_arr = self.get_gas_coal_eua_arr('eua', 'Y', moving_window, sD_fcst, eD_fcst)

        #combining into one df
        df=gas_arr.merge(eua_arr, how='inner', on='Date').reset_index()

        for i in range(moving_window):
            col_name = 'gas_mc' + '_dateminus' + str(i)
            df[col_name] = df['fwd_price_gasM1_dateminus' + str(i)] + 0.2 * df['fwd_price_euaY1_dateminus' + str(i)]

        # Create additional columns for each day in the moving window
        # These columns represent shifted forward prices
        df_out=df[['Date']+[x for x in df.columns if 'gas_mc_' in x]]

        return df_out

    def get_coal_mc_arr(self, moving_window=7, sD_fcst=None, eD_fcst=None):
        """
         Combines the already created partial function to give an estimate of marginal cost of coal
         for the given date while adjusting for a moving window period. The current formula used
         is coal_mc=coal/8.14 + eua*0.32

        Args:
            moving_window (int): The size of the moving window in days for calculating prices.
            sD_fcst (str): The start date of the forecast period in 'YYYY-MM-DD' format.
            eD_fcst (str): The end date of the forecast period in 'YYYY-MM-DD' format.

        Returns:
            pandas.DataFrame: A DataFrame containing the processed market data.
        """

        # Initial transformations and assertions

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str

        #calculating partial costs
        coal_arr = self.get_gas_coal_eua_arr('coal', 'M', moving_window, sD_fcst, eD_fcst)
        eua_arr = self.get_gas_coal_eua_arr('eua', 'Y', moving_window, sD_fcst, eD_fcst)

        #combining into one df
        df=coal_arr.merge(eua_arr, how='inner', on='Date').reset_index()

        for i in range(moving_window):
            col_name = 'coal_mc' + '_dateminus' + str(i)
            df[col_name] = df['fwd_price_coalM1_dateminus' + str(i)]/8.14 + 0.32 * df['fwd_price_euaY1_dateminus' + str(i)]

        # Create additional columns for each day in the moving window
        # These columns represent shifted forward prices
        df_out=df[['Date']+[x for x in df.columns if 'coal_mc_' in x]]

        return df_out

    def get_mcr_arr(self, moving_window=7, sD_fcst=None, eD_fcst=None):

        """
         Combines the already created partial function to give an estimate of marginal cost of resilduals
         for the given date while adjusting for a moving window period. The current formula used
         is mcr=gas_mc/coal_mc

        Args:
            moving_window (int): The size of the moving window in days for calculating prices.
            sD_fcst (str): The start date of the forecast period in 'YYYY-MM-DD' format.
            eD_fcst (str): The end date of the forecast period in 'YYYY-MM-DD' format.

        Returns:
            pandas.DataFrame: A DataFrame containing the processed market data.
        """

        # Initial transformations and assertions

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str

        #calculating partial costs
        gas_mc_arr = self.get_gas_mc_arr(moving_window, sD_fcst, eD_fcst)
        coal_mc_arr = self.get_coal_mc_arr(moving_window, sD_fcst, eD_fcst)

        #combining into one df
        df=gas_mc_arr.merge(coal_mc_arr, how='inner', on='Date').reset_index()

        for i in range(moving_window):
            col_name = 'mcr' + '_dateminus' + str(i)
            df[col_name] = df['coal_mc_dateminus' + str(i)]/df['gas_mc_dateminus' + str(i)]

        # Create additional columns for each day in the moving window
        # These columns represent shifted forward prices
        df_out=df[['Date']+[x for x in df.columns if 'mcr' in x]]

        return df_out
    
    
    #####################################
    """
    Functions for retrieving available capacity of production
    """
    @staticmethod
    def FTP_file_name(name):
        """
        Here set the names of FTP file in server to retrieve
        now useed primarily for AvCap fetch
        """
        my_dict = {}
        my_dict['de'] = '5044791_Pwr_PCA_PRO_AvailCap_EEX_REMIT_E1_DEU_F'
        return my_dict[name.lower()]
    
    def _load_config(self, PATH):
        
        with open(PATH, 'r') as file:
            config = json.load(file)['PointConnectFTP']
        self._username = config['USERNAME']
        self._password = config['PASSWORD']
    
    def PcFtpConnect(self):
        
        """
            Uses AvCapFetch_class (ACF) to initialize connection to FTP and process the raw
        data from FTP.
            
        """
        if os.path.exists('//etc-dc2k19/net/Algo/Database/configDB.json'):
            PATH = '//etc-dc2k19/net/Algo/Database/configDB.json'
        elif os.path.exists(r'Z:/EnergyTrading/configDB.json'):
            PATH = r'Z:/EnergyTrading/configDB.json'
        elif os.path.exists(r'C:/data/EnergyTrading/configDB.json'):
            PATH = r'C:/data/EnergyTrading/configDB.json'

        assert PATH, f'PATH not found!'

        FTP_SERVER = r'pointconnect.commodities.refinitiv.com'
        FTP_DIRECTORY_hist = '/PCO_Energy_Trading/PCO_Energy_Trading/History/Eur_Power/Supply/'
        FTP_DIRECTORY_live = '/PCO_Energy_Trading/PCO_Energy_Trading/Live/Eur_Power/Supply/'
        
        self._load_config(PATH)
        
        self._manager = ACF(ftp_server=FTP_SERVER, 
                                 username=self._username, 
                                 password=self._password)

        # Set directories where the data is stored
        self._manager.set_directories(directory_hist=FTP_DIRECTORY_hist, 
                                directory_live=FTP_DIRECTORY_live)
    @staticmethod
    def transform_AvCap_dict(nested_dict):
        """
            ACF class produces dict of values that needs to be tranformed to final df
        where index of the df are forecast dates/ trade dates with
        values in columns transposed from single columns for each fcst date
        
        """
        transformed_dict = {}    
        for key1, level1 in nested_dict.items():
            key1_dict = {}
            for key2, level2 in level1.items():
                transposed_dfs = []
                for key3, df in level2.items():
                    # Transpose the DataFrame
                    transposed_df = df.T    
                    # Rename columns
                    transposed_df.columns = ['av_cap_fcst_hour' + str(i+1)
                                             for i in range(len(transposed_df.columns))]    
                    # Set key3 as the index
                    transposed_df.index = [key3]    
                    transposed_dfs.append(transposed_df)    
                # Combine all transposed DataFrames for this key2
                combined_df = pd.concat(transposed_dfs)
                key1_dict[key2] = combined_df            
            transformed_dict[key1] = key1_dict    
        return transformed_dict
    
    
    def get_AvCap_dict(self,country='de',
                  asset_list=['lig', 'coal', 'gas'],
                  fcst_dim_list=['week_ahead'],
                  cut_off_time='12:00:00',
                  sD_fcst=None, eD_fcst=None):
        
        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str
        
        self._manager.set_substring(substring=self.FTP_file_name(country))
        self._manager.set_forecast_dates(start_date=sD_fcst, 
                                   end_date=eD_fcst,
                                   cut_off_time=cut_off_time)
        
        av_cap_dict = {}
        for date_range_type in fcst_dim_list:
            av_cap_dict[date_range_type] = {}
            for asset in ['gas', 'coal', 'lig']:
                self._manager.set_asset_id(asset)
                av_cap_dict[date_range_type][asset] = self._manager.to_hourly_series(date_range_type=date_range_type)
                
        return av_cap_dict

    def get_AvCap_df(self,country='de',
                  asset_list=['lig', 'coal', 'gas'],
                  fcst_dim_list=['week_ahead'],
                  cut_off_time='12:00:00',
                  sD_fcst=None, eD_fcst=None):
        """
            Output of the mehtod is df with forecast date/trade date as index
        and the columns are respective fcst dimension (week ahead, day ahead)
            Inputs:
                country/grid of interest,
                assets means plants/sources of production like coal, gas, ror(run-of-river)
                fcst_dim_list is forecast dimension meaning what future windows
                    are of interest example: week_ahead => for each forecast date the data starts
                    with the next nearest Monday and ends with next Sunday after the Monday
                cut_off_time is the latest time for each forecast date the ACF class
                    filter the data
                sD_fcst/eD_fcst are start and end of forecast dates
        """
        
        self.PcFtpConnect()

        if sD_fcst is None:
            sD_fcst = self._sD_str
        if eD_fcst is None:
            eD_fcst = self._eD_str
        
        self._manager.set_substring(substring=self.FTP_file_name(country))
        self._manager.set_forecast_dates(start_date=sD_fcst, 
                                   end_date=eD_fcst,
                                   cut_off_time=cut_off_time)
        av_cap_dict = self.get_AvCap_dict(country=country,
                                  asset_list=asset_list,
                                  fcst_dim_list=fcst_dim_list,
                                  cut_off_time=cut_off_time,
                                  sD_fcst=sD_fcst, eD_fcst=eD_fcst)
        return self.transform_AvCap_dict(av_cap_dict)
    
    def tagets_method():
        pass
    
    def data_compiler(self, predictors_dict,
                      targets_dict,
                      sD_fcst=None,
                      eD_fcst=None):
        """
        

        Parameters
        ----------
        predictors_dict : dict
            All the parameters that define the predictors.
        targets_dict : TYPE
            DESCRIPTION.
        sD_fcst : TYPE, optional
            DESCRIPTION. The default is None.
        eD_fcst : TYPE, optional
            DESCRIPTION. The default is None.

        Returns
        -------
        None.

        """
        pass
                     
        
    
    
        



#####################################


# if __name__ == '__main__':
    #any values will do for testing the single functions
    # start_date = dt.datetime(2023,10,20)
    # end_date = dt.datetime(2023,11,23)
    
    # predictors_dict = {
    #     'de_wa_rld_fct': {
    #         'get_RLD_fct': {
    #             'country': 'de',
    #             'fct_dim': 'da'}}}
    # targets_dict = {'target_1': {'targ_method': 'target_atribute'}}
    
    # data_obj = DataLoader(start_date, end_date,
    #                       predictors_dict,
    #                       targets_dict['target_1'])
    
    # test_df = data_obj.get_AvCap_df()
    
        

    # start_date = dt.datetime(2023, 9, 1)
    # end_date = dt.datetime(2023, 9, 5)
    # # test = rd_obj.selectHistoryRldData(start_date, end_date, 0)
    # predictors_dict = {
    #     'de_wa_rld_fct': {
    #         'get_RLD_fct': {
    #             'country': 'de',
    #             'fct_dim': 'da'}}}

    # targets_dict = {'target_1': {'targ_method': 'target_atribute'}}
    # df_name = 'wa_rld_fcst'
    # df_method = 'get_RLD_fcst'
    # data_obj = DataLoader(start_date, end_date,
    #                       predictors_dict,
    #                       targets_dict['target_1'])
    # # raw_rld = data_obj.get_RLD_raw()
    # # fcst_rld = data_obj.get_RLD_fcst()
    # # rld_norm = data_obj.get_RLD_normal()
    # # rld_raw_norm = data_obj.get_RLD_raw_normal()


