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

tol = 1e-6

class ExternalFundData(input_data):
        
    
    def __init__(self, params_dict, normalize_bool=False, ec_type='00'):
        super().__init__(params_dict)
        self._normalize_bool = normalize_bool
        self._ec_type = ec_type
        self.data_curve = {}
        self.data_curve_normalized = {}
        self.da_data = {}
        self.da_data_normalized = {}
        self.fut_periods  = None
        self.mid_fund_data = {}
        self.month_fund_data = {}
        self.normal_fund_data = {}
        self.mid_fund_matrix = {}
        self.month_fund_matrix = {}
        self.perc_fund_data = {}
        self.perc_fund_matrix = {}
        self.perc_curve = {}
        
        
    @property
    def normalize_bool(self):
        return self._normalize_bool
    
    @property
    def ec_type(self):
        return self._ec_type
    
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
        self.mid_fund_matrix = {}
        self.month_fund_matrix = {}
        self.perc_fund_matrix = {}
        
    def reset_data(self):
        self.mid_fund_data = {}
        self.month_fund_data = {}
        self.normal_fund_data = {}
        self.mid_fund_matrix = {}
        self.month_fund_matrix = {}
        self.data_curve = {}
        self.data_curve_normalized = {}
        self.da_data = {}
        self.da_data_normalized = {}
        self.perc_fund_data = {}
        self.perc_fund_matrix = {}
        self.perc_curve = {}
    
    # def transform_and_update_params_dict(self):
    #     new_params_dict = self.transform_params_dict(self.pivot_date)
    #     self.update_params_dict(new_params_dict)
    
    def get_mid_data(self):
        if dt.datetime.today().hour < 8:
            self._ec_type = '12'
        for market in self.unique_markets:
            if market not in self.mid_fund_data:
                temp = self.data_loader.get_fund_raw_data('mid',
                                                            self.fund_type,
                                                            self.ec_type,
                                                            market)
                if self.pivot_date.date not in temp['forecast_date'].dt.date:
                    temp_last_date = temp['forecast_date'].max()
                    last_date_data = temp.loc[temp['forecast_date']==temp_last_date].copy()
                    last_date_data['forecast_date'] += dt.timedelta(days=1)
                    temp = pd.concat([temp, last_date_data], ignore_index=True)
                    temp['forecast_date'] = temp['forecast_date'].dt.normalize()
                self._ec_type = '00'

                self.mid_fund_data[market] = temp.copy()
                
    def get_perc_data(self):
        for market in self.unique_markets:
            if market not in self.perc_fund_data:
                self.perc_fund_data[market] = {}
            for perc in [10,25,75,90]:
                self.perc_fund_data[market][perc] = self.data_loader.get_fund_raw_data(f"{perc}th",
                                                                                self.fund_type,
                                                                                self.ec_type,
                                                                                market)
    
    def get_month_data(self):
        for market in self.unique_markets:
            if market not in self.month_fund_data:
                self.month_fund_data[market] = self.data_loader.get_fund_raw_data('mnd',
                                                                                self.fund_type,
                                                                                self.ec_type,
                                                                                market)
    
    def get_normal_data(self):
        for market in self.unique_markets:
            if market not in self.normal_fund_data:
                market_source = enums.get_normal_data_source(market)
                self.normal_fund_data[market] = self.data_loader.get_fund_raw_data('normal',
                                                                            self.fund_type,
                                                                            self.ec_type,
                                                                            market,
                                                                            market_source).set_index('value_date')
    
    def get_fund_data(self):
        """
        Operate with self.fund_type from subclass
        """
        self.transform_and_update_params_dict()
        # Get first and last period to know the curve span
        self.get_curve_start_end_date
        if self.fut_periods is None:
            self.fut_periods = self.get_futures_periods()
        # Call fcst_types based on fut_periods
        # Mid forecast as default
        self.get_mid_data()
        self.get_perc_data()
        # Get the length of mid forecasts
        temp_mid = self.mid_fund_data[list(self.mid_fund_data)[0]].copy()
        temp_mid['periods_forward'] = (temp_mid['value_date'] - temp_mid['forecast_date']).dt.total_seconds() / 3600

        
        if max(temp_mid['periods_forward'])<self.fut_periods:
            self.get_month_data()
            temp_month = self.month_fund_data[list(self.month_fund_data)[0]].copy()
            temp_month['periods_forward'] = (temp_month['value_date'] - temp_month['forecast_date']).dt.total_seconds() / 3600

            if max(temp_month['periods_forward'])<self.fut_periods:
                self.get_normal_data()
        if self.normalize_bool:
            self.get_normal_data()
                
        
    
    def create_data_matrix(self, raw_df):
        if len(raw_df) < 1:
            return raw_df
        else:
            raw_df['hour'] = (raw_df['value_date'] - 
                                raw_df['forecast_date']).dt.total_seconds() / 3600
            pivot_df = pd.pivot_table(data=raw_df, columns='hour',
                                        index='forecast_date', values=self.fund_type)
            return pivot_df
        
    
    def get_data_matrix(self):
        self.get_fund_data()
        for market in self.unique_markets:
            if not market in self.mid_fund_matrix:
                data_matrix = self.create_data_matrix(self.mid_fund_data[market])
                self.mid_fund_matrix[market] = data_matrix
            if not market in self.month_fund_matrix:
                if market in self.month_fund_data:
                    data_matrix = self.create_data_matrix(self.month_fund_data[market])
                    self.month_fund_matrix[market] = data_matrix
            if not market in self.perc_fund_matrix:
                if market in self.perc_fund_data:
                    for perc in self.perc_fund_data[market]:
                        data_matrix = self.create_data_matrix(self.perc_fund_data[market][perc])
                        if len(data_matrix) > tol :
                            if not market in self.perc_fund_matrix:
                                self.perc_fund_matrix[market] = {}
                            self.perc_fund_matrix[market][perc] = data_matrix.copy()
    
    def get_perc_curve(self):
        self.get_data_matrix()
        
        for market, market_dict in self.perc_fund_matrix.items():
            if market not in self.perc_curve:
                self.perc_curve[market] = {}
            for perc, perc_df in market_dict.items():
                curve = perc_df.loc[self.pivot_date].dropna().copy()
                curve.index = self.pivot_date + pd.to_timedelta(curve.index,unit='h')
                self.perc_curve[market][perc] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
                
            
        
    def get_curve(self):
        self.get_data_matrix()
        for market in self.unique_markets:
            mid_curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()

            if len(mid_curve) <= self.fut_periods:
                
                if market not in ['es']:
                    month_curve = self.month_fund_matrix[market].copy()
                    if self.pivot_date not in month_curve.index:
                        month_curve = month_curve.loc[:self.pivot_date].iloc[-1].dropna().copy()
                    else:
                        month_curve = month_curve.loc[self.pivot_date].dropna().copy()                
                    curve = mid_curve.combine_first(month_curve)
                else:
                    curve = mid_curve.copy()
                if len(curve) <= self.fut_periods:
                    curve.index = self.pivot_date + pd.to_timedelta(curve.index,unit='h')
                    last_value = self.pivot_date + pd.to_timedelta(self.fut_periods,unit='h')
                    normal_curve = self.normal_fund_data[market].copy()
                    normal_curve = normal_curve.loc[curve.index[-1]:last_value].copy()
                    curve = curve.combine_first(normal_curve.iloc[:,0])
                    self.data_curve[market] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
                else:
                    curve.index = self.pivot_date + pd.to_timedelta(curve.index,unit='h')
                    self.data_curve[market] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
            else:
                curve = mid_curve.loc[:self.fut_periods].copy()
                curve.index = self.pivot_date + pd.to_timedelta(curve.index,unit='h')
                self.data_curve[market] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
            if self.normalize_bool:
                norm_curve = self.normal_fund_data[market].loc[self.data_curve[market].index[0]:
                    self.data_curve[market].index[-1]].copy()
                if self.fund_type in ['Solar']:
                    self.data_curve_normalized[market] = (self.data_curve[market]/
                                                        norm_curve).fillna(0)
                    self.data_curve_normalized[market]['Solar'] = np.where(self.data_curve_normalized[market]['Solar']>3,
                                                                3,
                                                                self.data_curve_normalized[market]['Solar'])
                else:
                    self.data_curve_normalized[market] = self.data_curve[market]/norm_curve

                
    def get_da_data(self):
        self.get_data_matrix()
        for market in self.unique_markets:
            temp_da = self.da_vector(self.mid_fund_matrix[market])
            self.da_data[market] = temp_da.loc[:(self.pivot_date+dt.timedelta(hours=23))].copy()
            if self.normalize_bool:
                norm_curve = self.normal_fund_data[market].copy()
                if 'value_date' in norm_curve.columns:
                    norm_curve = norm_curve.set_index('value_date').copy()
                norm_curve = norm_curve.loc[self.da_data[market].index[0]:
                    self.da_data[market].index[-1]].copy()
                if self.fund_type in ['Solar']:
                    self.da_data_normalized[market] = (self.da_data[market]/
                                                        norm_curve).fillna(0)
                    self.da_data_normalized[market]['Solar'] = np.where(self.da_data_normalized[market]>3,
                                                                3,
                                                                self.da_data_normalized[market])
                else:
                    self.da_data_normalized[market] = self.da_data[market]/norm_curve

    def update_mid_data(self):
        for market, market_mid_df in self.mid_fund_data.items():
            df1 = market_mid_df.copy()
            df2 = self.month_fund_data[market].copy()
            # Assuming df1 and df2 are the DataFrames
            # Columns are: ['forecast_date', 'value_date', 'Wind']

            # Step 1: Sort and ensure datetime columns are in the correct type
            df1['forecast_date'] = pd.to_datetime(df1['forecast_date'])
            df1['value_date'] = pd.to_datetime(df1['value_date'])
            df2['forecast_date'] = pd.to_datetime(df2['forecast_date'])
            df2['value_date'] = pd.to_datetime(df2['value_date'])

            # Step 2: Find the last forecast date in df1
            last_forecast_date = df1['forecast_date'].max()

            # Step 3: Filter df2 from the last forecast date onwards
            df2_filtered = df2[df2['forecast_date'] > last_forecast_date]

            # Step 4: Append the filtered part of df2 to df1
            combined_df = pd.concat([df1, df2_filtered], ignore_index=True)

            # Step 5: Sort the DataFrame by forecast_date and value_date if needed
            combined_df = combined_df.sort_values(by=['forecast_date', 'value_date']).reset_index(drop=True)
            self.mid_fund_data[market] = combined_df.copy()