"""
Subclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
from .consumption import Consumption as consumption
from .wind import Wind as wind
from .solar import Solar as solar
import pandas as pd
import datetime as dt
from fund_analysis.utils import ENUMS as enums

class ResidualDemand(external_fund_data):
    
    def __init__(self, params_dict, fund_type='ResidualDemand',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool, ec_type)
        self._fund_type = fund_type
        self.unique_markets_list = ['de', 'fr', 'be', 'nl', 'at']
    
    @property
    def fund_type(self):
        return self._fund_type
    
    @property
    def residual_demand_mapping(self):
        rd_map = {
            'ResidualDemand': [consumption, wind, solar],
            'CON_Wind': [consumption, wind],
            'CON_Solar': [consumption, solar],
            'CON': [consumption]
        }
        return rd_map
    
    def get_mid_data(self):
        for market in self.unique_markets:
            if market not in self.mid_fund_data:
                rd_source = enums.get_residual_demand_source(market)
                if rd_source.lower() in ['residualdemand']:
                    self.mid_fund_data[market] = self.data_loader.get_fund_raw_data('mid',
                                                                                self.fund_type,
                                                                                self.ec_type,
                                                                                market)
                    self.mid_fund_data[market].columns = ['forecast_date',
                                                            'value_date',
                                                            'ResidualDemand']
    
    def compile_rld_data(self, market, fcst_type):
        if fcst_type in ['mnd']:
            value_dates = ['forecast_date', 'value_date']
            data_source = 'db'
        elif fcst_type in ['normal']:
            value_dates = ['value_date']
            data_source  = enums.get_normal_data_source(market)        
        sources_data_dict = {}
        sources_data_dict[market] = {}
        rd_source = enums.get_residual_demand_source(market)
        for source in self.residual_demand_mapping[rd_source]:
            source_inst = source(self.original_params_dict,
                                    normalize_bool = self.normalize_bool,
                                    ec_type = self.ec_type)
            if market in ['at']:
                try:
                    sources_data_dict[market][source.__name__] = source_inst.data_loader.get_fund_raw_data(fcst_type,
                                                                                    source_inst.fund_type,
                                                                                    source_inst.ec_type,
                                                                                    market,
                                                                                    data_source)
                except:
                    sources_data_dict[market][source.__name__] = source_inst.data_loader.get_fund_raw_data('normal',
                                                                                    source_inst.fund_type,
                                                                                    source_inst.ec_type,
                                                                                    market,
                                                                                    'local')
            else:
                sources_data_dict[market][source.__name__] = source_inst.data_loader.get_fund_raw_data(fcst_type,
                                                                                source_inst.fund_type,
                                                                                source_inst.ec_type,
                                                                                market,
                                                                                data_source)
        if len(sources_data_dict[market]) == 3:
            # if market in ['at']:
            #     try:
            #         res = pd.merge(sources_data_dict[market]['Wind'],
            #                     sources_data_dict[market]['Solar'],
            #                     on='value_date',
            #                     how='inner')
            #     except:
            #         res = pd.merge(sources_data_dict[market]['Wind'],
            #                     sources_data_dict[market]['Solar'],
            #                     on=value_dates,
            #                     how='inner')
            # else:
            res = pd.merge(sources_data_dict[market]['Wind'],
                            sources_data_dict[market]['Solar'],
                            on=value_dates,
                            how='inner')
            res['res'] = res['Wind'] + res['Solar']
        elif len(sources_data_dict[market]) == 2:
            res_key = [a for a in list(sources_data_dict[market]) if a != 'Consumption']
            res = sources_data_dict[market][res_key]
            res['res'] = res[res_key]
        elif len(sources_data_dict[market]) == 1:
            # Assert that 'Consumption' is in the list
            assert 'Consumption' in sources_data_dict[market], "'Consumption' must be in the list"
            res = sources_data_dict[market]['Consumption'].copy()
            res['res'] = 0
            
        if res.index.name == 'value_date':
            res.reset_index(inplace=True)
        res = res[value_dates + ['res']].copy()

        rld = pd.merge(sources_data_dict[market]['Consumption'],
                        res[value_dates + ['res']],
                        on=value_dates,
                        how='inner')
        rld['ResidualDemand'] = rld['CON'] - rld['res']
        rld = rld[value_dates + ['ResidualDemand']].copy()
        if fcst_type == 'normal':
            rld.set_index('value_date', inplace=True)
        return rld
                
                
    def get_month_data(self):
        for market in self.unique_markets:
            if market not in self.month_fund_data:
                self.month_fund_data[market] = self.compile_rld_data(market, 'mnd')
    
    
    def get_normal_data(self):
        for market in self.unique_markets:
            if market not in self.normal_fund_data:
                self.normal_fund_data[market] = self.compile_rld_data(market, 'normal')
    
        