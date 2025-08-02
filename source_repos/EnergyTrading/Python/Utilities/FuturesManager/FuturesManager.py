# -*- coding: utf-8 -*-
"""
Created on Sat Aug 10 15:45:06 2024

@author: krajcovic
"""
from typing import Dict, Any, Optional

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from copy import deepcopy

from Utilities.FuturesManager.FuturesDataCollector import FuturesDataCollector
from Utilities.FuturesManager.FuturesDataProcessor import FuturesDataProcessor
from Utilities.FuturesManager.FuturesDataAnalyzer import FuturesDataAnalyzer


"""
This class is made for analysis of futures prices
Inputs:
    params_dict:
        dict
        relative references for selected reference date
Basic workflow:
    Data Collection:
        DB or Eikon or other source
    Data Processing:
        Wrangling
        Spread creations
        Working data ouput
    Data Analysis
    Data Output:
        DataFrames
        Charting
        Visualizations
        
Futures manager is Controler class

"""

class FuturesManager:
    
    def __init__(self, params_dict: dict = None):
        self._params_dict = params_dict
        
    
    @property
    def params_dict(self):
        return self._params_dict
    
    # Method for updatin params_dict directly
    def update_params_dict(self, new_params_dict: dict):
        self._params_dict = new_params_dict
    
    # If params dict is not directly inputed this method
    #   will create it from the basic inputs
    def create_params_dict(self,
                           relative_products: list,
                           market_list: list,
                           delivery_list: list,
                           reference_date: dt.datetime = None) -> dict:   
    
    
        # Generate the combinations
        products = []
        markets = []
        delivery = []    
        for product in relative_products:
            for market in market_list:
                for delivery_option in delivery_list:
                    products.append(product)
                    markets.append(market)
                    delivery.append(delivery_option)
        # Test this alternative
        # Generate the combinations using list comprehensions
            # products = [product for product in realtive_products for _ in market_list for _ in delivery_list]
            # markets = [market for _ in realtive_products for market in market_list for _ in delivery_list]
            # delivery = [delivery_option for _ in realtive_products for _ in market_list for delivery_option in delivery_list]
        # Fill in to dictionary
        params_dict = {}    
        params_dict['product_list'] = products    
        params_dict['market_list'] = markets    
        params_dict['delivery_list'] = delivery    
        # Legacy keys
        #params_dict['year_list'] = [None] * len(params_dict['market_list'])
        #params_dict['sD'] = None
        # If reference_date is None fetch last business day
        if reference_date is None:
            # Calculate the last business day
            today = dt.datetime.today()
            reference_date = pd.Timestamp(today.date()) - pd.offsets.BDay(1)
        params_dict['eD'] = reference_date
        
        self._params_dict = params_dict
        
    # Here insert method for finding specific ocntract
    # Insert absolute references with year list
    # Return params_dict with reative references
    # for the last trade date of contract
    def select_specific_contracts(self,
                                  absolute_products: list,
                                  market_list: list,
                                  delivery_list: list,
                                  year_list: list):
        pass
    
    
    # Method for collecting data from database
    
    def collect_data(self):
        fdc_inst = FuturesDataCollector(self.params_dict)
        raw_data_dict, selected_contracts_list = fdc_inst.get_data_from_database()
        return raw_data_dict, selected_contracts_list
    
    # Method for processing collected data
    # Output is dict with all spreads combinantions
    
    def process_data(self):
        raw_data_dict, selected_contracts_list = self.collect_data()
        
        fdp_inst = FuturesDataProcessor(self.params_dict,
                                        raw_data_dict)
        spread_data_dict = fdp_inst.create_spreads(selected_contracts_list)
        
        return spread_data_dict
        
    # Method for analysis of spreads
    
    # Mapping of analysis function to type of analysis
    @property
    def analysis_func_map(self):
        func_dict = {
            'bb_bands': lambda fda_inst: fda_inst.bollinger_bands(),
            'seasonality_adj' : lambda fda_inst: fda_inst.seasonality_adj()
            # Add other analysis types here, for example:
            # 'seasonality': lambda fda_inst: fda_inst.seasonality_analysis(),
        }
        return func_dict
    
    def analyze_data(self, analysis_type_list: list = ['all']):
        data_dict = {}
        spread_data_dict = self.process_data()
        fda_inst = FuturesDataAnalyzer(self.params_dict, spread_data_dict)
        
        # If 'all' is in the list, run all analysis functions
        if 'all' in analysis_type_list:
            analysis_type_list = list(self.analysis_func_map.keys())
        
        for analysis_type in analysis_type_list:
            if analysis_type in self.analysis_func_map:
                analysis_func = self.analysis_func_map[analysis_type]
                analysis_result = analysis_func(fda_inst)
                
                # If analysis type is 'bb_bands', group Level 3 keys
                if analysis_type == 'bb_bands':
                    grouped_result = self.group_level_3_keys(analysis_result)
                    data_dict[analysis_type] = grouped_result
                else:
                    data_dict[analysis_type] = analysis_result
            else:
                print(f"Warning: Analysis type '{analysis_type}' is not recognized.")
        
        return data_dict
    
    def group_level_3_keys(self, analysis_result):
        """
        This function groups the Level 3 keys under a new level based on their common parts.
        """
        grouped_dict = {}
    
        # Iterate over the Level 1 and Level 2 keys in the nested dictionary
        for level1_key, level2_dict in analysis_result.items():
            grouped_dict[level1_key] = {}
    
            for level2_key, level3_dict in level2_dict.items():
                # Create a new dictionary for the grouped keys at Level 3
                grouped_result = {}
    
                # Now we're grouping the Level 3 keys
                for key in level3_dict.keys():
                    # Group Level 3 keys by their common parts
                    if isinstance(key, tuple):
                        # Handle tuples by grouping each part
                        group_key = tuple('_'.join(k.split('_')[:-1]) for k in key)
                    else:
                        group_key = '_'.join(key.split('_')[:-1])
    
                    # Create a new dictionary level for each group
                    if group_key not in grouped_result:
                        grouped_result[group_key] = {}
    
                    # Add the original Level 3 key under the new group key
                    grouped_result[group_key][key] = level3_dict[key]
    
                # After grouping Level 3 keys, add them back to the Level 2 dictionary
                grouped_dict[level1_key][level2_key] = grouped_result
    
        return grouped_dict

    
    # def analyze_data(self, analysis_type_list: list = ['all']):
    #     data_dict = {}
    #     spread_data_dict = self.process_data()
    #     fda_inst = FuturesDataAnalyzer(self.params_dict, spread_data_dict)
        
    #     # If 'all' is in the list, run all analysis functions
    #     if 'all' in analysis_type_list:
    #         analysis_type_list = list(self.analysis_func_map.keys())
        
    #     for analysis_type in analysis_type_list:
    #         if analysis_type in self.analysis_func_map:
    #             analysis_func = self.analysis_func_map[analysis_type]
    #             data_dict[analysis_type] = analysis_func(fda_inst)
    #         else:
    #             print(f"Warning: Analysis type '{analysis_type}' is not recognized.")
        
    #     return data_dict
    
    def plot_data(self):
        data_dict = self.analyze_data()
        
        pass
        
        
        
            
if __name__== '__main__':
    pass
    base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
    base_products = ['M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3', 'Q_4',
                     'Q_5', 'Q_6','Y_1', 'Y_2', 'Y_3']
    base_products = ['M_1', 'M_2', 'Q_1', 'Q_2']
    market_list = ['de', 'fr', 'at', 'hu', 'cz', 'sk', 'hu', 'ro']
    market_list = ['de', 'fr']
    delivery_dict = ['base', 'peak']
    
    # Generate the combinations
    products = []
    markets = []
    delivery = []
    
    for product in base_products:
        for market in market_list:
            for delivery_option in delivery_dict:
                products.append(product)
                markets.append(market)
                delivery.append(delivery_option)
    
    params_dict = {}
    
    params_dict['product_list'] = products
    
    params_dict['market_list'] = markets
    
    params_dict['delivery_list'] = delivery 
    
    params_dict['year_list'] = [None] * len(params_dict['market_list'])
    params_dict['ns'] = 2
    params_dict['cont'] = False
    
    
    params_dict['sD'] = dt.datetime(2020,1,1)
    params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
    params_dict['eD'] = dt.datetime(2025,2,1)
    params_dict['ns'] = 2
    params_dict['cont'] = False
    
    
    fm_inst = FuturesManager(params_dict)
    
    # # raw_data = fm_inst.plot_data()
    
    data_dict = fm_inst.analyze_data()
    
    import pickle

    file_path = r'C:\data\Data\Data\Futures\data_dict.pkl'

    with open(file_path,'wb') as f:
        pickle.dump(data_dict, f)

    
    
    


        
        
        
        
