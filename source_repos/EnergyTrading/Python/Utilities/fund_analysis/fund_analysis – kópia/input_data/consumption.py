"""
Sobclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
import pandas as pd
import datetime as dt
from fund_analysis.utils import ENUMS as enums

class Consumption(external_fund_data):
    
    def __init__(self, params_dict, fund_type='CON',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool, ec_type)
        self._fund_type = fund_type
    
    @property
    def fund_type(self):
        return self._fund_type
    
    def adjust_normal(self):
        if not self.da_data:
            self.get_da_data()
        adj_dict = {}
        for market in self.unique_markets:
            if market not in self.da_data:
                self.get_da_data()
            temp = self.da_data[market].copy()
            temp = temp.iloc[-2*8760:].copy()
            norm_curve = self.normal_fund_data[market].copy()
            temp = pd.concat([temp, norm_curve],axis=1,join='inner')
            temp.columns = ['CON', 'norm']
            temp['CON_adj'] = temp['CON']/temp['norm']
            temp['month'] = temp.index.month
            temp = temp[['CON_adj', 'month']].copy()
            adj_dict[market] = temp.groupby('month').mean()
        return adj_dict
            
    
    def get_curve(self):
        self.get_data_matrix()
        adj_dict = self.adjust_normal()
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
                    normal_curve['month'] = normal_curve.index.month
                    normal_curve['CON'] = normal_curve['CON'] *\
                        normal_curve['month'].map(adj_dict['de']['CON_adj'])
                    normal_curve = normal_curve[['CON']].copy()
                    
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
                
                self.data_curve_normalized[market] = self.data_curve[market]/norm_curve
