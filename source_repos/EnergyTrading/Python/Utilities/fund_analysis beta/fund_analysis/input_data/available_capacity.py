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
import copy
import datetime as dt
from fund_analysis.utils import ENUMS as enums


class AvailableCapacityData(input_data):
    
    fut_periods  = None
    _ec_type = '12'
    
    def __init__(self, params_dict, cap_type,
                    fcst_time=dt.time(12,0,0),
                    unique_markets_list=[]):
        self.original_sD = copy.deepcopy(params_dict['sD'])
        params_dict['sD'] = min(dt.datetime(2019,1,1),
                                self.original_sD)
        super().__init__(params_dict)
        self._fcst_time = fcst_time
        self._cap_type = cap_type
        if len(unique_markets_list) < 1:
            self.unique_markets_list = ['de', 'fr', 'ro', 'hu']
        else:
            self.unique_markets_list = unique_markets_list
            
        self.cap_data = {}
        self.lt_inst_dict = {}
        self.cap_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        self.inst_cap_curves = {}
        
        
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
    def create_inst_cap_curve(df, value_date, curve=False):
        if curve:
            df = df.loc[df['forecast_date'].dt.date<=value_date.date()].copy()
        df = df.loc[df['forecast_date'].dt.date<=df['value_date'].dt.date].copy()
        df = df.sort_values('forecast_date')\
                .drop_duplicates(['value_date'],
                                    keep='last')\
                                        .set_index('value_date')\
                                            .sort_index()\
                                                .resample('h').ffill().copy()
        return df.loc[value_date:].drop(['forecast_date'], axis=1).copy()
    
    def get_da_data(self):
        self.get_cap_data()
        for market, market_df in self.cap_data.items():
            if not market in self.da_data:
                try:
                    market_df['forecast_date'] = pd.to_datetime(market_df['forecast_date'])
                except:
                    print('129')
                market_df['value_date'] = pd.to_datetime(market_df['value_date'])
                if enums.get_av_cap_mapping(self.cap_type) in ['InstCap']:
                    df = self.create_inst_cap_curve(market_df, self.original_sD)
                    df = df.loc[:self.pivot_date].iloc[:-1].copy()
                    self.da_data[market] = df
                else:
                    df = market_df.copy()
                    def get_da(group):
                        # Extract the first unique forecast_date and normalize it to 00:00:00
                        forecast_date = pd.to_datetime(group['forecast_date'].unique()[0]).normalize()
                        
                        # Drop 'forecast_date' column and work with the group
                        group = group.drop(['forecast_date'], axis=1).copy()
                        
                        # Set the 'value_date' as the index and resample to the minute, forward filling missing values
                        group = group.set_index('value_date').resample('min').ffill().copy()
                        
                        # Calculate the time difference between value_date and forecast_date in seconds
                        time_diff = (group.index - forecast_date).total_seconds()
                        
                        # Filter for rows where time difference is between 24 and 48 hours (86400 to 172800 seconds)
                        group = group[(time_diff >= 86400) & (time_diff < 172800)].copy()
                        
                        # Resample to hourly data and take the mean for each hour
                        group = group.resample('h').mean()
                        
                        return group
                    
                    # Group by forecast_date and resample
                    df = df.loc[df['forecast_date']>=self.original_sD].copy()
                    df_resampled = df.groupby('forecast_date').apply(get_da)
                    df_resampled = df_resampled.loc[self.original_sD:].copy()
                    df_resampled = df_resampled.sort_index(level=[0, 1], ascending=True)
                    # Step 2: Drop duplicates based on the second level of the index and keep the last
                    df_resampled = df_resampled[~df_resampled.index.droplevel(0).duplicated(keep='last')]
                    # Step 3: Drop rows where value_date is the same as forecast_date
                    df_resampled.index = df_resampled.index.droplevel('forecast_date')
                    self.da_data[market] = df_resampled
                
    def get_curve(self):
        self.get_cap_data()
        for market, df in self.cap_data.items():
            if not market in self.data_curve:
                if enums.get_av_cap_mapping(self.cap_type) in ['InstCap']:
                    lt_df = self.lt_inst_dict[market].copy()
                    df_curve = self.create_inst_cap_curve(df, self.pivot_date, True)
                    df_curve_lt = self.create_inst_cap_curve(lt_df, self.pivot_date, True)
                    df_curve = df_curve.combine_first(df_curve_lt)
                    self.data_curve[market] = df_curve.ffill()
                else:
                    self.data_curve[market] = self.create_inst_cap_curve(df, self.pivot_date, True)