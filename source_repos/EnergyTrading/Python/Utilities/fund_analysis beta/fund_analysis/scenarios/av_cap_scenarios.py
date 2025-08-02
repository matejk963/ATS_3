"""
Scenarios for Available Capacity
"""

from .scenarios import Scenarios as scenarios
import fund_analysis.input_data as input_data
import pandas as pd
import numpy as np
import datetime as dt
from fund_analysis.utils import ENUMS as enums


class AvCapScenarios(scenarios):
    av_cap_cols = []
    inst_data = {}
    
    def __init__(self, base_data,
                    params_dict,
                    data_type='av_cap',
                    unique_markets_list=[]):
        super().__init__(base_data)
        self._data_type = data_type
        self._params_dict = params_dict
        if len(unique_markets_list) < 1:
            self.unique_markets_list = ['de', 'fr', 'ro', 'hu']
        else:
            self.unique_markets_list = unique_markets_list
        self._inst_cap_inst = input_data.AvailableCapacityData(self.params_dict,
                                            'inst_cap')
        self._inst_cap_inst.set_pivot_date(self.curve_data['base'].index[0])
            
        
        
    @property
    def data_type(self):
        return self._data_type
    
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def inst_cap_inst(self):
        return self._inst_cap_inst
    
    def get_av_cap_columns(self):
        for market in self.unique_markets_list:
            long_name = enums.from_own_name(market)
            av_cap_cols_raw = enums.get_capacity_sources_for_market(long_name)
            av_cap_cols_market = [f'{av_cap}_{market}'
                                    for av_cap
                                    in av_cap_cols_raw]
            self.av_cap_cols.extend(av_cap_cols_market)
            self.av_cap_cols = list(np.unique(self.av_cap_cols))
    
    def get_inst_cap(self):
        self.inst_cap_inst.get_da_data()
        self.inst_cap_inst.get_curve()
        self.inst_data['da'] = pd.concat(self.inst_cap_inst.da_data,axis=1)
        self.inst_data['curve'] = pd.concat(self.inst_cap_inst.data_curve, axis=1)
        
    def get_historical_scenarios(self, scen_list):
        self.get_inst_cap()
        act_da = self.base_data['da']['base'].copy()
        inst_da = self.inst_data['da'].copy()
        
        inst_da.columns = inst_da.columns.droplevel(0)
        act_da = act_da[inst_da.columns].copy()
        inst_da = inst_da.reindex(act_da.index)
        util_da = act_da/inst_da
        act_da[util_da>1] = np.nan
        act_da = act_da.ffill()
        inst_da[util_da>1] = np.nan
        inst_da = inst_da.ffill()
        util_da = act_da/inst_da
        
        util_da['month'] = util_da.index.month
        scen_dict = {}
        for quant in scen_list:
            if quant in ['mean']:
                quant_name = f'AvailableCapacityData_mean'
                scen_dict[quant_name] = util_da.groupby('month').mean()
            else:
                quant_name = f'AvailableCapacityData_{int(round(quant*100))}th'
                scen_dict[quant_name] = util_da.groupby('month').quantile(quant)
            
        scen_dict['mean'] = util_da.groupby('month').mean()
        
        inst_curve = self.inst_data['curve']
        inst_curve.columns = inst_curve.columns.droplevel(0)
        inst_curve['month'] = inst_curve.index.month
        curve_scen_dict = {}
        for scen, scen_df in scen_dict.items():
            mapped_curve = inst_curve.apply(
                            lambda row: scen_df.loc[row['month']], axis=1
                        )
            curve_scen_dict[scen] = inst_curve.drop(columns=['month']) * mapped_curve
        inst_curve.drop(columns=['month'], inplace=True)
        
        self.get_av_cap_columns()
        av_cap_curve = self.curve_data['base'][self.av_cap_cols].dropna()
        
        
        
        return curve_scen_dict
    
    def fill_base_curve(self, mean_curve, inst_curve, fill_type='inst'):
        # Step 1: Calculate the adjusted mean curve
        if fill_type in ['mean']:
            exp_cap_ratio = pd.read_csv(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis\data\exp_cap_ratio.csv', index_col=0)
            ratio_curve = mean_curve.apply(lambda row: exp_cap_ratio.loc[row.name.month], axis=1)
            exp_mean_curve = mean_curve * ratio_curve
            exp_mean_curve = pd.DataFrame(
                np.where(exp_mean_curve > inst_curve, inst_curve, exp_mean_curve),
                index=mean_curve.index,
                columns=mean_curve.columns
            ).copy()
        elif fill_type in ['inst']:
            exp_mean_curve = inst_curve.copy()
        
        # Step 2: Identify the common index and common columns
        common_index = self.curve_data['base'].index.intersection(exp_mean_curve.index)
        common_columns = self.curve_data['base'].columns.intersection(exp_mean_curve.columns)
    
        # Step 3: Create a copy of `self.curve_data['base']` to be modified
        extended_base_curve = self.curve_data['base'].copy()
    
        # Step 4: Fill missing values in the copied DataFrame for the common index and columns
        extended_base_curve.loc[common_index, common_columns] = (
            extended_base_curve.loc[common_index, common_columns]
            .fillna(exp_mean_curve.loc[common_index, common_columns])
        )
    
        # Step 5: Return the extended curve
        return extended_base_curve
    
    def get_scenarios(self, scen_type:dict = {'historical':
        [a/100 for a in list(range(1,100))]}):
        if list(scen_type)[0] in ['historical']:
            return self.get_historical_scenarios(scen_list=\
                scen_type['historical'])
