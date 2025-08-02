"""
Sobclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
import pandas as pd
import datetime as dt
from fund_analysis.utils import ENUMS as enums

class Wind(external_fund_data):
    
    def __init__(self, params_dict, fund_type='Wind',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool=normalize_bool, ec_type=ec_type)
        self._fund_type = fund_type
        self.unique_markets_list=['ro']
        
    
    @property
    def fund_type(self):
        return self._fund_type
    
    # def update_mid_data(self):
    #     for market, market_mid_df in self.mid_fund_data.items():
    #         df1 = market_mid_df.copy()
    #         df2 = self.month_fund_data[market].copy()
    #         # Assuming df1 and df2 are the DataFrames
    #         # Columns are: ['forecast_date', 'value_date', 'Wind']

    #         # Step 1: Sort and ensure datetime columns are in the correct type
    #         df1['forecast_date'] = pd.to_datetime(df1['forecast_date'])
    #         df1['value_date'] = pd.to_datetime(df1['value_date'])
    #         df2['forecast_date'] = pd.to_datetime(df2['forecast_date'])
    #         df2['value_date'] = pd.to_datetime(df2['value_date'])

    #         # Step 2: Find the last forecast date in df1
    #         last_forecast_date = df1['forecast_date'].max()

    #         # Step 3: Calculate the difference between the first and last forecast dates of df2
    #         first_forecast_date_df2 = df2['forecast_date'].min()
    #         time_difference = last_forecast_date - first_forecast_date_df2

    #         # Step 4: Adjust the forecast dates in df2
    #         df2['forecast_date'] = df2['forecast_date'] + time_difference + pd.Timedelta(days=1)

    #         # Step 5: Concatenate df1 and df2
    #         combined_df = pd.concat([df1, df2], ignore_index=True)

    #         # Step 6: Sort the DataFrame by forecast_date and value_date if needed
    #         combined_df = combined_df.sort_values(by=['forecast_date', 'value_date']).reset_index(drop=True)

    #         self.mid_fund_data[market] = combined_df.copy()
        
    
    # def get_normal_data(self):
    #     for market in self.unique_markets:
    #         if market not in self.normal_fund_data:
    #             market_source = enums.get_normal_data_source(market)
    #             self.normal_fund_data[market] = self.data_loader.get_fund_raw_data('normal',
    #                                                                         self.fund_type,
    #                                                                         self.ec_type,
    #                                                                         market,
    #                                                                         market_source)