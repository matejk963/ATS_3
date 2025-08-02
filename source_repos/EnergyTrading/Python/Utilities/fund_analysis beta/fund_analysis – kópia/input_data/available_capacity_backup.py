"""

Class for handling External fundamental data
External:
    Consumption
    Intermitent production:
        Wind
        Solar
        Hydro
    Weather:
        Temperature
        Weather Regimes
        Oscilations & Teleconnections
        
Common functions:
    Processing raw data
    Creating curve(s) from mid/month/normal forecasts
    Normalizing data to normals
    
Main atributes that distinguish fundamentals:
    .fund_type : Wind/Solar/Cons/ResidualDemand/Hydro/Temp
    .fcst_type : mid/month/normal
    .ec_type : 00,06,12,18
    


"""

from .input_data import InputData as input_data
import pandas as pd
import numpy as np
import datetime as dt
from fund_analysis.utils import ENUMS as enums


class AvailableCapacityDataBackup(input_data):
    
    fut_periods  = None
    cap_data = {}
    cap_matrix = {}
    data_curve = {}
    da_data = {}
    _ec_type = '12'
    
    def __init__(self, params_dict, cap_type,
                    fcst_time=dt.time(12,0,0),
                    unique_markets_list=[]):
        super().__init__(params_dict)
        self._fcst_time = fcst_time
        self._cap_type = cap_type
        if len(unique_markets_list) < 1:
            self.unique_markets_list = ['de', 'fr']
        else:
            self.unique_markets_list = unique_markets_list
            
        self.cap_data = {}
        self.lt_inst_dict = {}
        self.cap_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        
        
    @property
    def fcst_time(self):
        return self._fcst_time
    
    @property
    def cap_type(self):
        return self._cap_type
    
    @property
    def ec_type(self):
        return self._ec_type
    
    def update_fcst_time(self, new_time: dt.time):
        self._fcst_time = new_time
        
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
        self.data_curve = {}
        self.da_data = {}
        
    def reset_data(self):
        self.cap_data = {}
        self.cap_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        
    def get_cap_data(self):
        for market in self.unique_markets:
            if not market in self.cap_data:
                cap_type_name = enums.get_av_cap_mapping(self.cap_type)
                market_name = enums.from_own_name(market)
                schema_name = f'FUND_{cap_type_name}'
                table_name = f'{market_name}_{self.ec_type}'
                self.cap_data[market] = self.data_loader.get_data_db(schema_name=schema_name,
                                                            table_name=table_name)
                if cap_type_name in ['InstCap']:
                    cap_type_name = 'LtInstCap'
                    market_name = enums.from_own_name(market)
                    schema_name = f'FUND_{cap_type_name}'
                    table_name = f'{market_name}_{self.ec_type}'
                    self.lt_inst_dict[market] = self.data_loader.get_data_db(schema_name=schema_name,
                                                                table_name=table_name)
                    
            
    @staticmethod
    def conditional_fill_pivot(pivot_df):
        """
        Function to process a pivoted DataFrame, filter columns closest to 12:00:00 for each date,
        and forward-fill NaN values to catch the latest update for each value_date.
        
        Parameters:
        pivot_df (pd.DataFrame): Pivoted DataFrame with `value_date` as index and `forecast_date` as columns.

        Returns:
        pd.DataFrame: Processed DataFrame with forward-filled values, where `value_date` is a regular column.
        """
        pivot_df.index = pd.to_datetime(pivot_df.index).floor('h')
        pivot_df = pivot_df.resample('h').mean()
        # Step 1: Create a new hourly index from the min to the max value_date
        hourly_index = pd.date_range(start=pd.to_datetime(pivot_df.index.min()), end=pivot_df.index.max(), freq='h')

        # Step 2: Reindex the DataFrame to hourly intervals without filling the missing values yet
        pivot_df_hourly = pivot_df.reindex(hourly_index)

        # Step 3: Select the column closest to 12:00:00 for each date
        forecast_times = pivot_df_hourly.columns

        # Create a mask where the value_date is greater than or equal to the forecast_date
        forecast_dates = pd.to_datetime(forecast_times.date)
        mask = np.greater_equal.outer(pd.to_datetime(pivot_df_hourly.index), forecast_dates)

        # Convert DataFrame to NumPy array for efficient processing
        values = pivot_df_hourly.to_numpy()

        # Step 4: Apply left-to-right fill (Horizontal pass)
        for i in range(1, values.shape[1]):
            # Ensure that we only forward-fill values where the value_date is greater than or equal to forecast_date
            values[:, i] = np.where(mask[:, i], np.where(np.isnan(values[:, i]), values[:, i - 1], values[:, i]), values[:, i])

        # Convert back to DataFrame
        filled_df = pd.DataFrame(values, index=pivot_df_hourly.index, columns=pivot_df_hourly.columns)

        # Step 5: Apply top-to-bottom fill (Vertical pass)
        filled_df = filled_df.ffill(axis=0)

        # Step 6: Apply another left-to-right fill to ensure all values are filled correctly
        values = filled_df.to_numpy()  # Convert DataFrame back to NumPy for efficiency
        for i in range(1, values.shape[1]):
            values[:, i] = np.where(mask[:, i], np.where(np.isnan(values[:, i]), values[:, i - 1], values[:, i]), values[:, i])

        # Convert back to DataFrame after the final left-to-right fill
        final_filled_df = pd.DataFrame(values, index=filled_df.index, columns=filled_df.columns)
        
        # Change columns to datetime "yyyy-mm-dd"
        final_filled_df.columns = [pd.to_datetime(a.date()) for a in final_filled_df.columns]
        return final_filled_df
    
    def get_curves_matrix(self):
        self.get_cap_data()
        temp_dict = {}
        for market in self.unique_markets:
            if not market in self.cap_matrix:
                cap_df = self.cap_data[market].copy()
                if enums.get_av_cap_mapping(self.cap_type) in ['InstCap']:
                    lt_cap_df = self.lt_inst_dict[market].copy()
                    # lt_cap_df = lt_cap_df.loc[:self.pivot_date].copy()
                    # lt_cap_df = lt_cap_df.loc[lt_cap_df.index.max()].reset_index().copy()
                temp_dict[market] = {}
                for source in cap_df.columns[2:]:
                    pivot_df = pd.pivot_table(cap_df[['forecast_date', 'value_date', source]],
                                    index='value_date', columns='forecast_date',
                                    values=source)
                    temp_dict[market][source] = self.conditional_fill_pivot(pivot_df=pivot_df)
                    if enums.get_av_cap_mapping(self.cap_type) in ['InstCap']:
                        if source in lt_cap_df.columns:
                            pivot_df = pd.pivot_table(lt_cap_df[['forecast_date', 'value_date', source]],
                                            index='value_date', columns='forecast_date',
                                            values=source)
                            lt_temp = self.conditional_fill_pivot(pivot_df=pivot_df)
                            extra_col = temp_dict[market][source].T.index[-1]+dt.timedelta(days=1)
                            lt_temp[extra_col] = np.nan
                            lt_temp = lt_temp.T.resample('D').ffill().T.copy()
                            lt_temp = lt_temp.drop([extra_col], axis=1)
                            temp_dict[market][source] = temp_dict[market][source].combine_first(lt_temp.T.resample('D').ffill().T)
                        else:
                            temp = temp_dict[market][source].T.copy()
                            temp[temp.columns[-1]+dt.timedelta(days=3650)] = np.nan
                            temp = temp.T.resample('h').ffill()
                            temp = temp.iloc[:-1].copy()
                            temp_dict[market][source] = temp.copy()
                self.cap_matrix = temp_dict
    
    @staticmethod
    def filter_day_ahead_values(filled_df):
        """
        Function to filter day-ahead values from a DataFrame where value_date (index)
        is exactly one day after forecast_date (column).
        
        Parameters:
        filled_df (pd.DataFrame): A DataFrame where the index is value_date and columns are forecast_date.
        
        Returns:
        pd.Series: A single time series combining day-ahead values.
        """
        # Convert index and columns to `datetime.date` if they aren't already
        index_dates = pd.to_datetime(filled_df.index).date
        column_dates = pd.to_datetime(filled_df.columns)

        # Create a mask where the index is exactly one day after the column date
        mask = np.equal.outer(index_dates, (column_dates + pd.Timedelta(days=1)).date)

        # Apply the mask to the DataFrame to filter day-ahead values
        day_ahead_df = pd.DataFrame(
            np.where(mask, filled_df, np.nan),  # Keep values where mask is True, otherwise NaN
            index=filled_df.index,
            columns=filled_df.columns
        )

        # Forward fill to combine into a single time series, ensuring the most recent forecast is kept
        single_series = day_ahead_df.bfill(axis=1).iloc[:, 0]

        return single_series
    
    def get_da_data(self):
        self.get_curves_matrix()
        for market, market_dict in self.cap_matrix.items():
            if not market in self.da_data:
                source_da_data_list = []
                for source, source_df in market_dict.items():
                    temp_da = self.filter_day_ahead_values(source_df).dropna()
                    temp_da.name = source
                    last_value = self.pivot_date + dt.timedelta(hours=23)
                    temp_da = temp_da.loc[:last_value].copy()
                    if not temp_da.empty:
                        source_da_data_list.append(temp_da)
                source_da_data = pd.concat(source_da_data_list,
                                            axis=1)
                self.da_data[market] = source_da_data
                
    def get_curve(self):
        self.get_curves_matrix()
        for market, market_dict in self.cap_matrix.items():
            if not market in self.data_curve:
                source_curves_list = []
                for source, source_df in market_dict.items():
                    curve = source_df.loc[:,self.pivot_date].dropna().copy()
                    curve.name = source
                    # last_value = self.pivot_date + dt.timedelta(days=366, hours=-1)
                    self.fut_periods = self.get_futures_periods()
                    last_value = self.pivot_date + dt.timedelta(hours=self.fut_periods)
                    curve = curve.loc[:last_value].copy()
                    if len(curve) > 0:
                        source_curves_list.append(curve)
                source_curves_df = pd.concat(source_curves_list,
                                                axis=1)
                self.data_curve[market] = source_curves_df