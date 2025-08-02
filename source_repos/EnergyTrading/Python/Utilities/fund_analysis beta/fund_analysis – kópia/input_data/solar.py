"""
Sobclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
import pandas as pd
import datetime as dt
from fund_analysis.utils import ENUMS as enums
import numpy as np
import copy

class Solar(external_fund_data):
    
    def __init__(self, params_dict, fund_type='Solar',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool=normalize_bool,
                            ec_type=ec_type)
        self._fund_type = fund_type
    
    @property
    def fund_type(self):
        return self._fund_type
    
    # def get_normal_data(self):
    #     for market in self.unique_markets:
    #         if market not in self.normal_fund_data:
    #             market_source = enums.get_normal_data_source(market)
    #             self.normal_fund_data[market] = self.data_loader.get_fund_raw_data('normal',
    #                                                                         self.fund_type,
    #                                                                         self.ec_type,
    #                                                                         market,
    #                                                                         market_source)
    
    def get_curve(self):
        self.get_data_matrix()
        for market in self.unique_markets:
            mid_curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()
            if len(mid_curve) <= self.fut_periods:
                month_curve = self.month_fund_matrix[market].copy()
                if self.pivot_date not in month_curve.index:
                    month_curve = month_curve.loc[:self.pivot_date].iloc[-1].dropna().copy()
                else:
                    month_curve = month_curve.loc[self.pivot_date].dropna().copy()                
                curve = mid_curve.combine_first(month_curve)
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
                df = copy.deepcopy(self.data_curve[market])
                self.data_curve_normalized[market] = copy.deepcopy(df)
                df = pd.concat([df, norm_curve],axis=1)
                df.columns = ['Solar', 'norm']
                df_index = df.index
                df = df.resample('D').mean()
                df['Solar_nmz'] = df['Solar']/df['norm']
                df = df[['Solar_nmz']].reindex(df_index, method='ffill')
                df['Solar_nmz'] = np.where(norm_curve.reindex(df.index,method='ffill').squeeze()==0,0,df['Solar_nmz'].values)
                # Step 3: Create the normalized column using vectorized operations
                self.data_curve_normalized[market]['Solar'] = df['Solar_nmz']
                del df
                del norm_curve

    
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
                df = copy.deepcopy(self.da_data[market])
                self.da_data_normalized[market] = copy.deepcopy(df)
                df = pd.concat([df, norm_curve],axis=1)
                df.columns = ['Solar', 'norm']
                df_index = df.index
                df = df.resample('D').mean()
                df['Solar_nmz'] = df['Solar']/df['norm']
                df = df[['Solar_nmz']].reindex(df_index, method='ffill')
                df['Solar_nmz'] = np.where(norm_curve.reindex(df.index,method='ffill').squeeze()==0,0,df['Solar_nmz'].values)
                # Step 3: Create the normalized column using vectorized operations
                self.da_data_normalized[market]['Solar'] = df['Solar_nmz']
                del df
                del norm_curve