"""
Sobclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
import pandas as pd
import numpy as np
import datetime as dt
from fund_analysis.utils import ENUMS as enums

class Temp(external_fund_data):
    
    def __init__(self, params_dict, fund_type='Temp',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool=normalize_bool,
                            ec_type=ec_type)
        self._fund_type = fund_type
        self.unique_markets_list = ['hu']
    
    @property
    def fund_type(self):
        return self._fund_type
    
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
        # Get the length of mid forecasts
        temp_mid = self.mid_fund_data[list(self.mid_fund_data)[0]].copy()
        temp_mid['periods_forward'] = (temp_mid['value_date'] - temp_mid['forecast_date']).dt.total_seconds() / 3600
                
        if max(temp_mid['periods_forward'])<self.fut_periods:
            self.get_normal_data()
        if self.normalize_bool:
            self.get_normal_data()
    
    def get_curve(self):
        self.get_data_matrix()
        for market in self.unique_markets:
            mid_curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()
            curve = mid_curve.loc[:self.fut_periods].copy()
            
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
    
    # def get_normal_data(self):
    #     for market in self.unique_markets:
    #         if market not in self.normal_fund_data:
    #             market_source = enums.get_normal_data_source(market)
    #             self.normal_fund_data[market] = self.data_loader.get_fund_raw_data('normal',
    #                                                                         self.fund_type,
    #                                                                         self.ec_type,
    #                                                                         market,
    #                                                                         market_source)