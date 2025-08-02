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
import concurrent.futures
import copy
import concurrent.futures
import copy
import pandas as pd

tol = 1e-6

class ResidualDemand(external_fund_data):
    
    def __init__(self, params_dict, fund_type='ResidualDemand',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool, ec_type)
        self._fund_type = fund_type
        self.unique_markets_list = ['de', 'fr', 'be', 'nl', 'at', 'es']
    
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
        if dt.datetime.today().hour < 8:
            self._ec_type = '12'
        for market in self.unique_markets:
            if market not in self.mid_fund_data:
                rd_source = enums.get_residual_demand_source(market)
                if rd_source.lower() in ['residualdemand']:
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
                    self.mid_fund_data[market].columns = ['forecast_date',
                                                            'value_date',
                                                            'ResidualDemand']
    def get_perc_data(self):
        for market in self.unique_markets:
            if market not in self.perc_fund_data:
                self.perc_fund_data[market] = {}
            rd_source = enums.get_residual_demand_source(market)
            if rd_source.lower() in ['residualdemand']:
                for perc in [10,25,75,90]:
                    self.perc_fund_data[market][perc] = self.data_loader.get_fund_raw_data(f"{perc}th",
                                                                                    self.fund_type,
                                                                                    self.ec_type,
                                                                                    market)
                    if len(self.perc_fund_data[market][perc].columns) > tol:
                        self.perc_fund_data[market][perc].columns = ['forecast_date',
                                                                'value_date',
                                                                'ResidualDemand']
                        
    # def get_fund_data(self):
    #     """
    #     Operate with self.fund_type from subclass
    #     """
    #     self.transform_and_update_params_dict()
    #     # Get first and last period to know the curve span
    #     self.get_curve_start_end_date
    #     if self.fut_periods is None:
    #         self.fut_periods = self.get_futures_periods()
    #     # Call fcst_types based on fut_periods
    #     # Mid forecast as default
    #     self.get_mid_data()
    #     self.get_perc_data()
    #     self.get_normal_data()
    
    # def create_data_matrix(self, raw_df):
    #     if len(raw_df) < 1:
    #         return raw_df
    #     else:
    #         raw_df['hour'] = (raw_df['value_date'] - 
    #                             raw_df['forecast_date']).dt.total_seconds() / 3600
    #         pivot_df = pd.pivot_table(data=raw_df, columns='hour',
    #                                     index='forecast_date', values=self.fund_type)
    #         return pivot_df
        
    
    # def get_data_matrix(self):
    #     self.get_fund_data()
    #     for market in self.unique_markets:
    #         if not market in self.mid_fund_matrix:
    #             data_matrix = self.create_data_matrix(self.mid_fund_data[market])
    #             self.mid_fund_matrix[market] = data_matrix
    #         if not market in self.perc_fund_matrix:
    #             if market in self.perc_fund_data:
    #                 for perc in self.perc_fund_data[market]:
    #                     data_matrix = self.create_data_matrix(self.perc_fund_data[market][perc])
    #                     if len(data_matrix) > tol :
    #                         if not market in self.perc_fund_matrix:
    #                             self.perc_fund_matrix[market] = {}
    #                         self.perc_fund_matrix[market][perc] = data_matrix.copy()
    


    # def get_curve(self):
    #     self.get_data_matrix()

    #     # Function to process each market independently
    #     def process_market(market):
    #         mid_curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()
    #         if len(mid_curve) <= self.fut_periods:
    #             sources_data_dict = {}
    #             rd_source = enums.get_residual_demand_source(market)
    #             for source in self.residual_demand_mapping[rd_source]:
    #                 source_inst = source(self.original_params_dict,
    #                                     normalize_bool=self.normalize_bool,
    #                                     ec_type=self.ec_type)
    #                 source_inst.unique_markets_list = self.unique_markets
    #                 source_inst.get_curve()
    #                 sources_data_dict[source.__name__] = copy.deepcopy(source_inst.data_curve)

    #             temp = pd.concat(
    #                 [sources_data_dict[source_key][market] for source_key in sources_data_dict.keys()],
    #                 axis=1,  # Concatenate along columns
    #                 join='outer'  # Adjust join type (outer, inner, etc.)
    #             )

    #             temp['rld'] = temp['CON'] - temp['Wind'] - temp['Solar']

    #             curve = mid_curve.copy()
    #             curve.index = self.pivot_date + pd.to_timedelta(curve.index, unit='h')
    #             curve = curve.combine_first(temp['rld'])
    #             self.data_curve[market] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
    #             if self.normalize_bool:
    #                 norm_curve = self.normal_fund_data[market].loc[self.data_curve[market].index[0]:
    #                                                             self.data_curve[market].index[-1]].copy()
    #                 self.data_curve_normalized[market] = self.data_curve[market] / norm_curve

    #     # Use ThreadPoolExecutor to process markets concurrently
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         executor.map(process_market, self.unique_markets)


    # def get_curve(self):
    #     self.get_data_matrix()
        
    #     # Cache dictionary to store computed data_curve for each (source, market) pair
    #     cache = {}

    #     for market in self.unique_markets:
    #         mid_curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()
    #         if len(mid_curve) <= self.fut_periods:
    #             sources_data_dict = {}
    #             rd_source = enums.get_residual_demand_source(market)
    #             for source in self.residual_demand_mapping[rd_source]:
    #                 # Check if the data for this source and market is already cached
    #                 source.__name__
    #                 if source.__name__ in cache:
    #                     # Use the cached data if available
    #                     sources_data_dict[source.__name__] = cache[source.__name__]
    #                 else:
    #                     # Otherwise, create a new instance and compute the curve
    #                     source_inst = source(self.original_params_dict,
    #                                         normalize_bool=self.normalize_bool,
    #                                         ec_type=self.ec_type)
    #                     source_inst.unique_markets_list = self.unique_markets
    #                     source_inst.get_curve()
    #                     # Store the result in the cache for future use
    #                     cache[source.__name__] = copy.deepcopy(source_inst.data_curve)
    #                     sources_data_dict[source.__name__] = cache[source.__name__]

    #             temp = pd.concat(
    #                 [sources_data_dict[source_key][market] for source_key in sources_data_dict.keys()],
    #                 axis=1,  # Concatenate along columns
    #                 join='outer'  # Adjust join type (outer, inner, etc.)
    #             )

    #             temp['rld'] = temp['CON'] - temp['Wind'] - temp['Solar']

    #             curve = mid_curve.copy()
    #             curve.index = self.pivot_date + pd.to_timedelta(curve.index, unit='h')
    #             curve = curve.combine_first(temp['rld'])
    #             self.data_curve[market] = pd.DataFrame(curve).rename(columns={curve.name: self.fund_type})
    #         self.get_normal_data()

    #         if self.normalize_bool:
    #             norm_curve = self.normal_fund_data[market].loc[self.data_curve[market].index[0]:
    #                                                         self.data_curve[market].index[-1]].copy()
    #             self.data_curve_normalized[market] = self.data_curve[market] / norm_curve
    
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
            # if market in ['at', 'es']:
            #     try:
            #         sources_data_dict[market][source.__name__] = source_inst.data_loader.get_fund_raw_data(fcst_type,
            #                                                                         source_inst.fund_type,
            #                                                                         source_inst.ec_type,
            #                                                                         market,
            #                                                                         data_source)
            #     except:
            #         sources_data_dict[market][source.__name__] = source_inst.data_loader.get_fund_raw_data('normal',
            #                                                                         source_inst.fund_type,
            #                                                                         source_inst.ec_type,
            #                                                                         market,
            #                                                                         data_source)
            # else:
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
                if market not in ['es']:
                    self.month_fund_data[market] = self.compile_rld_data(market, 'mnd')
    
    
    def get_normal_data(self):
        for market in self.unique_markets:
            if market not in self.normal_fund_data:
                self.normal_fund_data[market] = self.compile_rld_data(market, 'normal')
    
        