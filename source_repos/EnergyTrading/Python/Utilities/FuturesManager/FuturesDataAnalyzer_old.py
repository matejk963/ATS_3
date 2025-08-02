# -*- coding: utf-8 -*-
"""
Created on Sat Aug 10 20:04:58 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
from copy import deepcopy

from Utilities.FuturesManager.FuturesDataCollector import FuturesDataCollector
from Utilities.FuturesManager.FuturesDataProcessor import FuturesDataProcessor

from functools import wraps
from itertools import combinations
import itertools
from collections import defaultdict


"""
    Class for analyzing grouped spreads
    Input:
        params_dict
        raw_data_dict from FuturesDataProcessor
    
    Output:
        out_data_dict:
            mimic the structure of spread_dict from FDP,
            insert global analysis into the structure
            spread_type:
                country_level/combination:
                    contract combination:
                        analysis type:
                            df with data of analysis
            global_analysis_types:
                css/ghr correlation matrices for each market pairs
    Types of analysis:
        correlation
        regression
        translation to current fuel costs
        seasonality/historical comparison
        TA indicators computation:
            candles
            MAs
            Kalman
            BB

"""


class FuturesDataAnalyzer:
    
    def __init__(self, params_dict: dict,
                 work_dict: dict):
        self._params_dict = params_dict
        self._work_dict = work_dict
        
    @property
    def params_dict(self):
        return self._params_dict
    
   
    @property
    def work_dict(self):
        return self._work_dict
    
    
    # Bollinger Bands
    def bollinger_bands(self, kalman=True):
        bb_dict = {}
        
        for spread_type, spread_type_dict in self.work_dict.items():
            bb_dict[spread_type] = {}
            for spread_type_spec, spread_type_spec_dict in spread_type_dict.items():
                bb_dict[spread_type][spread_type_spec] = {}
                for spread, spread_df in spread_type_spec_dict.items():
                    if len(spread_df)<1:
                        continue
                    spread_df.sort_index(inplace=True)
                    price_data = spread_df[spread_type]['spread_value'].copy()
                    ratio_data = spread_df[spread_type]['spread_ratio'].copy()
                    
                    if kalman:
                        price_data_est = self.kalman_filter_fair_price(price_data)
                        ratio_data_est = self.kalman_filter_fair_price(ratio_data)
                    else:
                        price_data_est = self.ema_with_std(price_data)
                        ratio_data_est = self.ema_with_std(ratio_data)
                    
                    # Add original data to the estimates DataFrame
                    price_data_est = pd.concat([price_data.rename('spread_value'), price_data_est], axis=1)
                    ratio_data_est = pd.concat([ratio_data.rename('spread_ratio'), ratio_data_est], axis=1)
                    
                    # Merge spread_value and spread_ratio into a single DataFrame
                    merged_df = pd.concat({
                        'spread_value': price_data_est,
                        'spread_ratio': ratio_data_est
                    }, axis=1)
                    
                    # Store the merged DataFrame in bb_dict
                    bb_dict[spread_type][spread_type_spec][spread] = merged_df
        
        # Save the bb_dict if required

        
        return bb_dict
    
    
    # Historical ratio analysis
    # Aproximate historical values based on ratio to gas on the current gas prices
    
    def approximate_history(self):
        # Retrieve contracts ratios
        ratios_dict = self.spread_parts_selection()
        
        # Retrieve gas prices
        gas_dict = self.spread_parts_selection(level_0_col_substring='TTF', level_1_col='settlement_price')
        
        # Retrieve EUA prices
        eua_dict = self.spread_parts_selection(level_0_col_substring='EUA', level_1_col='settlement_price')
        
        # Initialize result dictionary
        result_dict = {}
        
        # Iterate over the keys in ratios_dict
        for key in ratios_dict:
            result_dict[key] = {}
            for subkey in ratios_dict[key]:
                result_dict[key][subkey] = {}
                for contract in ratios_dict[key][subkey]:
                    # Extract DataFrames from each dictionary
                    df_ratios = ratios_dict[key][subkey][contract]
                    df_gas = gas_dict[key][subkey][contract]
                    df_eua = eua_dict[key][subkey][contract]
                    
                    # Ensure there are numeric years in the level 1 columns for gas, eua, and ratios DataFrames
                    gas_contracts = df_gas.columns.get_level_values(0).unique()
                    eua_contracts = df_eua.columns.get_level_values(0).unique()
                    ratio_contracts = df_ratios.columns.get_level_values(0).unique()
                    
                    # Find the last year for each contract
                    latest_years_gas = {contract: max(df_gas[contract].columns) for contract in gas_contracts}
                    latest_years_eua = {contract: max(df_eua[contract].columns) for contract in eua_contracts}
                    latest_years_ratio = {contract: max(df_ratios[contract].columns) for contract in ratio_contracts}
                    
                    # Adjust the DataFrames for gas, eua, and ratios to use the latest years
                    df_gas_latest = pd.concat([df_gas.xs(latest_years_gas[contract], axis=1, level=1) for contract in gas_contracts], axis=1)
                    df_eua_latest = pd.concat([df_eua.xs(latest_years_eua[contract], axis=1, level=1) for contract in eua_contracts], axis=1)
                    
                    df_gas_adjusted = pd.DataFrame(index=df_gas_latest.index)
                    df_eua_adjusted = pd.DataFrame(index=df_eua_latest.index)
                    
                    df_ratios_adjusted = pd.DataFrame()
                    ratio_contracts_df = pd.DataFrame()
                    for contract in ratio_contracts:
                        latest_year = latest_years_ratio[contract]
                        shift_years = int(latest_years_gas[contract]) - int(latest_year)
                        shifted_ratio = df_ratios.xs(latest_year, axis=1, level=1).shift(periods=shift_years * 365, freq='D').dropna()
                        if ratio_contracts_df.empty:
                            ratio_contracts_df = shifted_ratio.copy()
                        else:
                            ratio_contracts_df = pd.concat([ratio_contracts_df, shifted_ratio], axis=1)
                            
                    if ratio_contracts_df.columns.nlevels == 1:
                        try:
                            ratio_contracts_df.columns = pd.MultiIndex.from_product([[ratio_contracts], [latest_year]])
                        except:
                            pass
                            
                    if df_ratios_adjusted.empty:
                        df_ratios_adjusted = ratio_contracts_df.copy()
                    else:
                        df_ratios_adjusted = pd.concat([df_ratios_adjusted, ratio_contracts_df], axis=1)
            
                    # Calculate the weighted sum of gas and eua prices
                    if key in ['calendar_spreads']:
                        pass
                    weighted_sum = df_gas_latest.add(df_eua_latest * 0.2)
    
                    # Ensure the weighted_sum DataFrame is not empty before proceeding
                    if not weighted_sum.dropna().empty:
                        first_date = weighted_sum.dropna().index[0]
                        last_date = weighted_sum.dropna().index[-1]
                        
                        # Multiply the weighted sum by the aligned ratios DataFrame
                        try:
                            reconstructed_price = weighted_sum.mul(df_ratios_adjusted).loc[first_date:last_date].interpolate().copy()
                        except Exception as e:
                            print(f"Error processing contract {contract}: {e}")
                            reconstructed_price = None
                    else:
                        print(f"No valid data for contract {contract}. Skipping.")
                        reconstructed_price = None
                            
                    # Store the result in the result_dict
                    result_dict[key][subkey][contract] = reconstructed_price
        
        # Return the result dictionary
        return result_dict
    

    # def approximate_history(self):
    #     # Retrieve contracts ratios
    #     ratios_dict = self.spread_parts_selection()
        
    #     # Retrieve gas prices
    #     gas_dict = self.spread_parts_selection(level_0_col_substring='TTF', level_1_col='settlement_price')
        
    #     # Retrieve EUA prices
    #     eua_dict = self.spread_parts_selection(level_0_col_substring='EUA', level_1_col='settlement_price')
        
    #     # Initialize result dictionary
    #     result_dict = {}
        
    #     # Iterate over the keys in ratios_dict
    #     for key in ratios_dict:
    #         result_dict[key] = {}
    #         for subkey in ratios_dict[key]:
    #             result_dict[key][subkey] = {}
    #             for contract in ratios_dict[key][subkey]:
    #                 # Extract DataFrames from each dictionary
    #                 df_ratios = ratios_dict[key][subkey][contract]
    #                 df_gas = gas_dict[key][subkey][contract]
    #                 df_eua = eua_dict[key][subkey][contract]
                    
    #                 # Ensure there are numeric years in the level 1 columns for gas, eua, and ratios DataFrames
    #                 gas_years = [col for col in df_gas.columns.get_level_values(1) if col.isdigit()]
    #                 eua_years = [col for col in df_eua.columns.get_level_values(1) if col.isdigit()]
    #                 ratio_years = [col for col in df_ratios.columns.get_level_values(1) if col.isdigit()]
                    
    #                 if not gas_years or not eua_years or not ratio_years:
    #                     raise ValueError(f"No valid year columns found for contract '{contract}' in '{key}-{subkey}'.")
                    
    #                 latest_year_gas = max(gas_years)
    #                 latest_year_eua = max(eua_years)
                    
    #                 df_gas_latest = df_gas.xs(latest_year_gas, axis=1, level=1)
    #                 df_eua_latest = df_eua.xs(latest_year_eua, axis=1, level=1)
                    
    #                 # Adjust the index to account for the time shift for previous years
    #                 df_gas_adjusted = pd.DataFrame(index=df_gas_latest.index)
    #                 df_eua_adjusted = pd.DataFrame(index=df_eua_latest.index)
                    
  
    #                 # Shift ratio columns based on the year difference from the latest year
    #                 df_ratios_adjusted = pd.DataFrame()
    #                 for year in np.unique(ratio_years):
    #                     shift_years = int(latest_year_gas) - int(year)
    #                     shifted_ratio = df_ratios.xs(year, axis=1, level=1).shift(periods=shift_years * 365, freq='D').dropna()
                        
    #                     if shifted_ratio.columns.nlevels == 1:
    #                         contract_name = df_ratios.columns.get_level_values(0)[0]
    #                         shifted_ratio.columns = pd.MultiIndex.from_product([shifted_ratio.columns, [year]])
                            
    #                     if df_ratios_adjusted.empty:
    #                         df_ratios_adjusted = shifted_ratio.copy()
    #                     else:                        
    #                         df_ratios_adjusted = pd.concat([df_ratios_adjusted, shifted_ratio], axis=1)
    
    #                 # Calculate the weighted sum of gas and eua prices
    #                 if key in ['calendar_spreads']:
    #                     pass
    #                 weighted_sum = df_gas_latest.add(df_eua_latest * 0.2)
    #                 first_date = weighted_sum.dropna().index[0]
    #                 last_date = weighted_sum.dropna().index[-1]
                    
    #                 # Multiply the weighted sum by the aligned ratios DataFrame
    #                 try:
    #                     reconstructed_price = weighted_sum.mul(df_ratios_adjusted).loc[first_date:last_date].interpolate().copy()
    #                 except:
    #                     pass
                    
    #                 # Store the result in the result_dict
    #                 result_dict[key][subkey][contract] = reconstructed_price
        
    #     # Return the result dictionary
    #     return result_dict
    
    

    def spread_parts_selection(self, level_0_col_substring='css', level_1_col='spread_ratio'):
    
        part_dict = {}
    
        # Get css groups for spread ratio
        css_dict = self.work_dict['css']['css']
        css_contracts = list(css_dict)
        css_groups = self.group_elements(css_contracts)
    
        part_dict['css'] = {}
        part_dict['css']['css'] = {}
    
        # Special handling for the 'css' spread type: select columns containing the substring in level 0 and concatenate by groups
        for group, group_comb in css_groups.items():
            group_dfs = []
    
            for key in group_comb:
                df = css_dict[key]
                year = key.split('_')[-1]  # Extract the year part
                contract_name = '_'.join(key.split('_')[:-1])  # Extract the contract name without the year
    
                # Select columns where level 0 contains the substring and level 1 matches the specified column
                df_selected = df.loc[:, (df.columns.get_level_values(0).str.contains(level_0_col_substring)) & 
                                          (df.columns.get_level_values(1) == level_1_col)]
                
                # Rename columns: level 0 as contract name without year, level 1 as the year
                df_selected.columns = pd.MultiIndex.from_tuples([(contract_name, year)], names=['contract', 'year'])
                group_dfs.append(df_selected)
    
            if group_dfs:
                # Concatenate all selected DataFrames for this group
                concatenated_group_df = pd.concat(group_dfs, axis=1)
    
                # Ensure there are no redundant levels
                if concatenated_group_df.columns.nlevels > 2:
                    concatenated_group_df.columns = concatenated_group_df.columns.droplevel(0)
    
                # Store this concatenated DataFrame under the group key in part_dict['css']
                part_dict['css']['css'][group] = concatenated_group_df
    
        for spread_type, spread_type_dict in self.work_dict.items():
            # Skip 'css' since it has been processed already
            if spread_type == 'css':
                continue
    
            part_dict[spread_type] = {}
            for spread_type_spec, spread_type_spec_dict in spread_type_dict.items():
                part_dict[spread_type][spread_type_spec] = {}
                contracts = list(spread_type_spec_dict)
                groups_dict = self.group_elements(contracts)
                for group, group_comb in groups_dict.items():
    
                    if len(group) == 2:
                        # Retrieve the DataFrames for both keys in the group
                        df1 = part_dict['css']['css'][group[0]]
                        df2 = part_dict['css']['css'][group[1]]
    
                        # Concatenate these DataFrames
                        combined_df = pd.concat([df1, df2], axis=1, keys=[group[0], group[1]])
    
                        # Drop any third-level column (if exists)
                        if combined_df.columns.nlevels > 2:
                            combined_df.columns = combined_df.columns.droplevel(0)
    
                    # Save the meta_group under the group key in part_dict
                    if len(combined_df) > 0:
                        part_dict[spread_type][spread_type_spec][group] = combined_df
    
        return part_dict

    
                   
    # def spread_parts_selection(self, level_0_col_substring='css', level_1_col='spread_ratio'):

    #     part_dict = {}
    
    #     # Get css groups for spread ratio
    #     css_dict = self.work_dict['css']['css']
    #     css_contracts = list(css_dict)
    #     css_groups = self.group_elements(css_contracts)
    
    #     part_dict['css'] = {}
    #     part_dict['css']['css'] = {}
    
    #     # Special handling for the 'css' spread type: select columns containing the substring in level 0 and concatenate by groups
    #     for group, group_comb in css_groups.items():
    #         group_dfs = []
    
    #         for key in group_comb:
    #             df = css_dict[key]
    #             year = key.split('_')[-1]  # Extract the year part
    
    #             # Select columns where level 0 contains the substring and level 1 matches the specified column
    #             df_selected = df.loc[:, (df.columns.get_level_values(0).str.contains(level_0_col_substring)) & 
    #                                       (df.columns.get_level_values(1) == level_1_col)]
                
    #             # Rename columns with the year
    #             df_selected.columns = pd.MultiIndex.from_product([[year], df_selected.columns.get_level_values(1)])
    #             group_dfs.append(df_selected)
    
    #         if group_dfs:
    #             # Concatenate all selected DataFrames for this group
    #             concatenated_group_df = pd.concat(group_dfs, axis=1)
    
    #             # Drop any third-level column (if exists)
    #             if concatenated_group_df.columns.nlevels > 2:
    #                 concatenated_group_df.columns = concatenated_group_df.columns.droplevel(2)
    
    #             # Store this concatenated DataFrame under the group key in part_dict['css']
    #             part_dict['css']['css'][group] = concatenated_group_df
    
    #     for spread_type, spread_type_dict in self.work_dict.items():
    #         # Skip 'css' since it has been processed already
    #         if spread_type == 'css':
    #             continue
    
    #         part_dict[spread_type] = {}
    #         for spread_type_spec, spread_type_spec_dict in spread_type_dict.items():
    #             part_dict[spread_type][spread_type_spec] = {}
    #             contracts = list(spread_type_spec_dict)
    #             groups_dict = self.group_elements(contracts)
    #             for group, group_comb in groups_dict.items():
    
    #                 if len(group) == 2:
    #                     # Retrieve the DataFrames for both keys in the group
    #                     df1 = part_dict['css']['css'][group[0]]
    #                     df2 = part_dict['css']['css'][group[1]]
    
    #                     # Concatenate these DataFrames
    #                     combined_df = pd.concat([df1, df2], axis=1, keys=[group[0], group[1]])
    
    #                     # Drop any third-level column (if exists)
    #                     if combined_df.columns.nlevels > 2:
    #                         combined_df.columns = combined_df.columns.droplevel(2)
    
    #                 # Save the meta_group under the group key in part_dict
    #                 if len(combined_df) > 0:
    #                     part_dict[spread_type][spread_type_spec][group] = combined_df
    
    #     return part_dict  
    
    @staticmethod
    def group_elements(elements):
        def normalize(element):
            # Remove the last part after the last underscore
            return "_".join(element.split("_")[:-1])
        groups = defaultdict(list)
        
        for item in elements:
            if isinstance(item, tuple):
                # Normalize each element in the tuple and create a normalized key
                key = tuple(normalize(x) for x in item)
                groups[key].append(item)
            else:
                # Normalize single elements and create a normalized key
                key = normalize(item)
                groups[key].append(item)
        
        return dict(groups)
    
    

                    
                

        
        
    # Kalman Filter fair price estimate
    @staticmethod
    def kalman_filter_fair_price(price_series, process_variance=1e-2, measurement_variance=1, std_smoothing_factor=0.95):
        """
        Computes the fair price using a Kalman filter and returns the fair price along with
        smoothed upper and lower bands based on the difference between the observed prices and the fair price estimate.
    
        Parameters:
        - price_series (pd.Series): Time series of prices.
        - process_variance (float): Variance of the process noise.
        - measurement_variance (float): Variance of the measurement noise.
        - std_smoothing_factor (float): Smoothing factor for the std estimate (default is 0.9).
    
        Returns:
        - fair_price_series (pd.Series): Series of fair prices estimated by the Kalman filter.
        - upper_band (pd.Series): Upper band at fair price + 2*smoothed std.
        - lower_band (pd.Series): Lower band at fair price - 2*smoothed std.
        """
        price_series = price_series.ffill().bfill()  # Handle missing data
        
        n = len(price_series)
        fair_price_estimates = np.zeros(n)
        std_estimates = np.zeros(n)
        
        initial_estimate = price_series.iloc[0]
        fair_price_estimates[0] = initial_estimate
        estimate_covariance = 1.0
        
        Q = process_variance
        R = measurement_variance
        
        for t in range(1, n):
            prior_estimate = fair_price_estimates[t-1]
            prior_covariance = estimate_covariance + Q
            
            if np.isnan(price_series.iloc[t]):
                fair_price_estimates[t] = prior_estimate
                std_estimates[t] = std_estimates[t-1]  # Keep the previous std estimate if NaN
                continue
            
            K = prior_covariance / (prior_covariance + R)
            fair_price_estimates[t] = prior_estimate + K * (price_series.iloc[t] - prior_estimate)
            estimate_covariance = (1 - K) * prior_covariance
            
            # Update the std estimate based on the difference between observed price and the estimated price
            raw_std_estimate = np.abs(price_series.iloc[t] - fair_price_estimates[t])
            
            # Apply smoothing to the standard deviation estimate
            std_estimates[t] = std_smoothing_factor * std_estimates[t-1] + (1 - std_smoothing_factor) * raw_std_estimate
        
        fair_price_series = pd.Series(fair_price_estimates, index=price_series.index)
        std_estimates_series = pd.Series(std_estimates, index=price_series.index)
        
        upper_band = fair_price_series + 2 * std_estimates_series
        lower_band = fair_price_series - 2 * std_estimates_series
        
        kalman_out = pd.concat([lower_band,
                                fair_price_series,
                                upper_band], axis=1)
        kalman_out.columns = ['lower_band', 'mean', 'upper_band']
        
        
        return kalman_out
    
    
    @staticmethod
    def ema_with_std(price_series, span=20, std_smoothing_factor=0.9):
        """
        Computes the Exponential Moving Average (EMA) of the price series and returns the EMA along with
        smoothed upper and lower bands based on the difference between the observed prices and the EMA.
    
        Parameters:
        - price_series (pd.Series): Time series of prices.
        - span (int): The span for the EMA calculation.
        - std_smoothing_factor (float): Smoothing factor for the std estimate (default is 0.9).
    
        Returns:
        - ema_series (pd.Series): Series of EMA estimates.
        - upper_band (pd.Series): Upper band at EMA + 2*smoothed std.
        - lower_band (pd.Series): Lower band at EMA - 2*smoothed std.
        """
        ema_series = price_series.ewm(span=span, adjust=False).mean()  # Calculate EMA
        
        n = len(price_series)
        std_estimates = np.zeros(n)
        
        # Calculate initial std estimate
        initial_std_estimate = np.abs(price_series.iloc[0] - ema_series.iloc[0])
        std_estimates[0] = initial_std_estimate
        
        for t in range(1, n):
            raw_std_estimate = np.abs(price_series.iloc[t] - ema_series.iloc[t])
            
            # Apply smoothing to the standard deviation estimate
            std_estimates[t] = std_smoothing_factor * std_estimates[t-1] + (1 - std_smoothing_factor) * raw_std_estimate
        
        std_estimates_series = pd.Series(std_estimates, index=price_series.index)
        
        upper_band = ema_series + 2 * std_estimates_series
        lower_band = ema_series - 2 * std_estimates_series
        
        ema_out = pd.concat([lower_band,
                                ema_series,
                                upper_band], axis=1)
        ema_out.columns = ['lower_band', 'mean', 'upper_band']
        
        return ema_out


        

        
        
        
if __name__== '__main__':
    params_dict = {}
    # params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1']*6
    # params_dict['market_list'] = ['de'] * 6 + ['fr'] * 6 + ['hu'] * 6
    # params_dict['delivery_list'] = ['base']*3 + ['peak'] * 3 +['base']*3 + ['peak'] * 3 + ['base']*3 + ['peak'] * 3
    # params_dict['eD'] = dt.datetime(2024,8,9)  
    
    params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1', 'Y_2']*4
    params_dict['market_list'] = ['de'] * 8 + ['fr']*8
    params_dict['delivery_list'] = ['base']*4 + ['peak'] * 4 + ['base']*4 + ['peak'] * 4
    params_dict['eD'] = dt.datetime(2024,8,9)  
    
    fdc = FuturesDataCollector(params_dict)  
    raw_data = fdc.get_data_from_database()    
    fdp = FuturesDataProcessor(params_dict, raw_data)    
    spread_data_dict = fdp.create_spreads()
    
    fda = FuturesDataAnalyzer(params_dict, spread_data_dict)
    
    # bb_dict = fda.bollinger_bands(kalman=False)
    aprox_hist = fda.approximate_history()
        
        
        
        
        
    