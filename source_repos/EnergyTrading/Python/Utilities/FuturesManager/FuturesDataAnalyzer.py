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
                    if len(spread_df) < 1:
                        continue

                    spread_df.sort_index(inplace=True)

                    if spread_type == 'outright_contracts':
                        # Only one column: 'settlement_price'
                        price_data = spread_df['settlement_price'].copy()

                        if kalman:
                            price_data_est = self.kalman_filter_fair_price(price_data)
                        else:
                            price_data_est = self.ema_with_std(price_data)

                        # Add original data to the estimates DataFrame
                        price_data_est = pd.concat([price_data.rename('settlement_price'), price_data_est], axis=1)

                        # Create a two-level column structure
                        price_data_est.columns = pd.MultiIndex.from_product(
                            [['value'], price_data_est.columns]
                        )

                        # Store the processed DataFrame in bb_dict
                        bb_dict[spread_type][spread_type_spec][spread] = price_data_est
                    else:
                        # Handle cases with 'spread_value' and 'spread_ratio'
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
        
    def filter_and_process_combinations(self):
        filtered_dict = {}
    
        # Iterate through the work_dict
        for key in self.work_dict:
            if key in ['outright_contracts']:
                continue
            filtered_dict[key] = {}
            for subkey in self.work_dict[key]:
                filtered_dict[key][subkey] = {}
                for comb, comb_df in self.work_dict[key][subkey].items():
                    
                    # Determine if comb is a tuple or a single element
                    if isinstance(comb, tuple):
                        # For tuples, check the earliest delivery_start date
                        delivery_start_dates = []
                        for element in comb:
                            grid, delivery, product, start_month, year = element.split('_')
                            delivery_start_date = self.get_delivery_start_date(delivery, product, start_month, year)
                            delivery_start_dates.append(delivery_start_date)
                        
                        earliest_delivery_start = min(delivery_start_dates)
                    else:
                        # For single elements
                        grid, delivery, product, start_month, year = comb.split('_')
                        earliest_delivery_start = self.get_delivery_start_date(delivery, product, start_month, year)
                    
                    # Compare earliest_delivery_start with self.params_dict['eD']
                    if earliest_delivery_start > self.params_dict['eD']:
                        # If the delivery start is after the specified date, keep the combination
                        filtered_dict[key][subkey][comb] = comb_df
    
        return filtered_dict
    
    def get_delivery_start_date(self, delivery, product, start_month, year):
        # Ensure the year and month are properly formatted for pd.to_datetime
        year_full = f"20{year}"  # Assuming all years are 2000+
        month_padded = start_month.zfill(2)  # Pad single-digit months with a zero
    
        if product in ['M', 'Q']:
            delivery_start = pd.to_datetime(f'{year_full}-{month_padded}-01')
        
        elif product == 'S':
            # For season: 1 means April (Spring), 2 means October (Fall)
            delivery_start = pd.to_datetime(f'{year_full}-04-01' if start_month == '1' else f'{year_full}-10-01')
        elif product == 'Y':
            delivery_start = pd.to_datetime(f'{year_full}-01-01')
        else:
            raise ValueError(f"Unknown product type: {product}")
        
        return delivery_start
    
    def process_and_shift_spread_ratios(self, filtered_dict):
        result_dict = {}
    
        # Iterate through the filtered dictionary
        for key in filtered_dict:
            if key in ['calendar_spreads']:
                pass
            result_dict[key] = {}
            for subkey in filtered_dict[key]:
                result_dict[key][subkey] = {}
                for comb, comb_df in filtered_dict[key][subkey].items():
                    result_dict[key][subkey][comb] = {}
    
                    if isinstance(comb, tuple):
                        elements = comb
                    else:
                        elements = [comb]
    
                    # To store concatenated DataFrame for the comb
                    concat_dfs = []
    
                    for element in elements:
                        # Extract the element substring without the year part
                        element_parts = element.split('_')
                        element_substring = '_'.join(element_parts[:-1])
                        main_contract_year = int(element_parts[-1])

                        for market, market_dict in self.work_dict['css'].items():
                            # Filter work_dict['css'][market] to find matching contracts
                            for contract_key, contract_df in market_dict.items():
                                if element_substring in contract_key:
                                    df_css = contract_df.copy()
        
                                    # Extract the year from the contract key
                                    contract_parts = contract_key.split('_')
                                    contract_year = int(contract_parts[-1])
        
                                    # Calculate the number of years to shift
                                    shift_years = main_contract_year - contract_year
        
                                    # Select only the 'spread_ratio' columns and shift
                                    try:
                                        spread_ratio_data = df_css.loc[:, (df_css.columns.get_level_values(0).str.contains('css')) & 
                                                                            ((df_css.columns.get_level_values(1) == 'spread_ratio')|
                                                                            (df_css.columns.get_level_values(1) == 'spread_value'))]
        
                                        # Apply the shift to align the spread ratio with the main contract year
                                        spread_ratio_data = spread_ratio_data.shift(periods=shift_years * 365, freq='D')
        
                                        # Interpolate NaN values
                                        # spread_ratio_data = spread_ratio_data.interpolate(method='linear')
        
                                        # Rename columns to have level 0 as the contract and level 1 as 'spread_ratio'
                                        # spread_ratio_data.columns = pd.MultiIndex.from_product([[contract_key], ['spread_value','spread_ratio']])
                                        spread_ratio_data.columns = pd.MultiIndex.from_tuples(
                                                        [(contract_key, level_1) for _,
                                                        level_1 in spread_ratio_data.columns]
                                                    )
                                        concat_dfs.append(spread_ratio_data.interpolate(method='linear'))
                                    except KeyError:
                                        print(f"Could not find 'spread_ratio' for contract {contract_key}.")
        
                    # Concatenate the results for all matching contracts
                    if concat_dfs:
                        result_df = pd.concat(concat_dfs, axis=1).interpolate(method='linear',
                                                                            limit=5,
                                                                            limit_area='inside')
                        
                        result_dict[key][subkey][comb] = result_df
        
        return result_dict

    def get_actual_contracts(self, filtered_dict):
        result_dict = {}
    
        # Iterate through the filtered dictionary
        for key in filtered_dict:
            result_dict[key] = {}
            for subkey in filtered_dict[key]:
                result_dict[key][subkey] = {}
                for comb, comb_df in filtered_dict[key][subkey].items():
                    result_dict[key][subkey][comb] = {}
    
                    if isinstance(comb, tuple):
                        elements = comb
                    else:
                        elements = [comb]
                    
                    # To store concatenated DataFrame for the comb
                    concat_dfs = []
    
                    for element in elements:
                        css_data = None
                        ttf_data = None
                        eua_data = None
                        
                        # Retrieve the corresponding DataFrame from work_dict['css'][market]
                        for market, market_dict in self.work_dict['css'].items():
                            if element in market_dict:
                                df_css = market_dict[element]
        
                                # Select the required columns for css and spread_ratio
                                try:
                                    css_data = df_css.loc[:, (df_css.columns.get_level_values(0).str.contains('css')) & 
                                                                (df_css.columns.get_level_values(1) == 'spread_ratio')]
                                    css_data.columns = pd.MultiIndex.from_product([[element], ['spread_ratio']])
                                except KeyError:
                                    print(f"Could not find 'css' and 'spread_ratio' for {element}.")
        
                                # Select the settlement_price columns for TTF
                                try:
                                    ttf_data = df_css.loc[:, (df_css.columns.get_level_values(0).str.contains('TTF')) & 
                                                                (df_css.columns.get_level_values(1) == 'settlement_price')]
                                    ttf_data.columns = pd.MultiIndex.from_product([[element], ['gas_price']])
                                except KeyError:
                                    print(f"Could not find 'TTF' and 'settlement_price' for {element}.")
        
                                # Select the settlement_price columns for EUA
                                try:
                                    eua_data = df_css.loc[:, (df_css.columns.get_level_values(0).str.contains('EUA')) & 
                                                                (df_css.columns.get_level_values(1) == 'settlement_price')]
                                    eua_data.columns = pd.MultiIndex.from_product([[element], ['eua_price']])
                                except KeyError:
                                    print(f"Could not find 'EUA' and 'settlement_price' for {element}.")
                        
                        # Concatenate the columns for the current element
                        if css_data is not None or ttf_data is not None or eua_data is not None:
                            concatenated = pd.concat([css_data, ttf_data, eua_data], axis=1)
                            concat_dfs.append(concatenated)
    
                    # Concatenate the results for all elements in comb
                    if concat_dfs:
                        result_df = pd.concat(concat_dfs, axis=1)
                        result_dict[key][subkey][comb] = result_df
        
        return result_dict
    
    def combine_and_multiply(self, shifted_spread_ratios_dict, current_contracts_dict):
        result_dict = {}
    
        # Iterate through the keys in shifted_spread_ratios_dict
        for key in shifted_spread_ratios_dict:
            result_dict[key] = {}
            for subkey in shifted_spread_ratios_dict[key]:
                result_dict[key][subkey] = {}
                for comb in shifted_spread_ratios_dict[key][subkey]:
                    
                    # Get the corresponding DataFrame from the shifted spread ratios dict
                    spread_ratios_df = shifted_spread_ratios_dict[key][subkey][comb]
                    
                    elements = comb if isinstance(comb, tuple) else [comb]
                    
                    # Prepare to store the final result for this comb
                    final_df = pd.DataFrame()
    
                    # Determine the full index range from both spread_ratios_df and current_contracts_dict
                    full_index = spread_ratios_df.index.union(
                        current_contracts_dict[key][subkey][comb].index
                    )
    
                    # Get the corresponding DataFrames from current_contracts_dict based on level 0 column index
                    element_columns = current_contracts_dict[key][subkey][comb].columns.get_level_values(0).unique()
    
                    for contract in element_columns:
                        gas_df = current_contracts_dict[key][subkey][comb].xs('gas_price', axis=1, level=1)[[contract]]
                        eua_df = current_contracts_dict[key][subkey][comb].xs('eua_price', axis=1, level=1)[[contract]]
    
                        # Align these DataFrames with the full index to ensure no data is lost
                        gas_df = gas_df.reindex(full_index)
                        eua_df = eua_df.reindex(full_index)
    
                        # Calculate the weighted sum: gas + 0.2 * eua
                        weighted_sum = gas_df + 0.2 * eua_df

                        # Multiply each spread ratio with the weighted sum
                        for hist_contract in spread_ratios_df.columns.get_level_values(0):
                            if contract.split('_')[:-1] == hist_contract.split('_')[:-1]:
                                # Extract spread_ratio column
                                contract_df = spread_ratios_df[[(hist_contract, 'spread_ratio'),
                                                                (hist_contract, 'spread_value')]]    
                                # Check if contract_df is a DataFrame and drop duplicate columns
                                if isinstance(contract_df, pd.DataFrame):
                                    contract_df = contract_df.loc[:, ~contract_df.columns.duplicated()].copy()    
                                # Align the contract_df with the full index
                                contract_df = contract_df.reindex(full_index)    
                                # Align the indices of contract_df and weighted_sum before multiplication
                                aligned_contract_df, aligned_weighted_sum = contract_df.align(
                                    weighted_sum.squeeze(), join='inner', axis=0
                                )    
                                # Ensure aligned_contract_df is a Series, even if it was originally a single-column DataFrame
                                aligned_contract_df = aligned_contract_df.squeeze()    
                                # Ensure indices align and multiply
                                multiplied_series = aligned_contract_df[(hist_contract,
                                                                          'spread_ratio')]\
                                    * aligned_weighted_sum
                                # Interpolate approx_price up to its last valid value
                                approx_price_series = multiplied_series.copy()
                                try:
                                    approx_price_series_last_valid = approx_price_series.dropna().index[-1]
                                except:
                                    pass
                                approx_price_series.interpolate(method='linear', inplace=True)    
                                # Only mask values if there is a valid last date
                                try:
                                    approx_price_series[approx_price_series.index >= approx_price_series_last_valid] = pd.NA
                                except:
                                    pass    
                                # Create a DataFrame for approx_price with the correct MultiIndex
                                approx_price_df = approx_price_series.to_frame(name=(hist_contract, 'approx_price'))    
                                # Adjust spread_ratio to have correct MultiIndex
                                # contract_df = aligned_contract_df.to_frame(name=(hist_contract, 'spread_ratio'))    
                                # Concatenate the spread_ratio and approx_price DataFrames
                                combined_df = pd.concat([contract_df, approx_price_df], axis=1)
    
                                # Concatenate the result to the final DataFrame
                                if final_df.empty:
                                    final_df = combined_df.copy()
                                else:
                                    final_df = pd.concat([final_df, combined_df], axis=1)
                    
                    # If comb is a tuple, apply specific logic based on the breakdown
                    if isinstance(comb, tuple):
                        spread_df = pd.DataFrame(index=full_index)
                    
                        # Extract the years directly from the level_0 columns
                        level_0_columns = final_df.columns.get_level_values(0)
                        unique_years = sorted(set(col.rsplit('_', 1)[-1] for col in level_0_columns))
                    
                        # Logic to differentiate between spreading within the same year and between consecutive years
                        first_part_A, second_part_A = comb[0].rsplit('_', 1)
                        first_part_B, second_part_B = comb[1].rsplit('_', 1)
                    
                        if first_part_A == first_part_B:
                            # Same first part, handle consecutive years
                            for i in range(len(unique_years) - 1):
                                year_A = unique_years[i]
                                year_B = unique_years[i + 1]
                    
                                col_A = f'{first_part_A}_{year_A}'
                                col_B = f'{first_part_B}_{year_B}'
                    
                                if col_A in final_df.columns.get_level_values(0) and col_B in final_df.columns.get_level_values(0):
                                    # Drop duplicate columns if any
                                    final_df = final_df.loc[:, ~final_df.columns.duplicated()]
                    
                                    spread_ratio = final_df[(col_A, 'spread_ratio')] - final_df[(col_B, 'spread_ratio')]
                                    approx_price = final_df[(col_A, 'approx_price')] - final_df[(col_B, 'approx_price')]
                                    spread_value = final_df[(col_A, 'spread_value')] - final_df[(col_B, 'spread_value')]
                    
                                    # Ensure the subtraction results in Series and assign to spread_df
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'spread_ratio')] = spread_ratio.squeeze()
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'approx_price')] = approx_price.squeeze()
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'spread_value')] = spread_value.squeeze()
                    
                        elif second_part_A == second_part_B:
                            # Different first parts, handle within the same year
                            for year in unique_years:
                                col_A = f'{first_part_A}_{year}'
                                col_B = f'{first_part_B}_{year}'
                    
                                if col_A in final_df.columns.get_level_values(0) and col_B in final_df.columns.get_level_values(0):
                                    # Drop duplicate columns if any
                                    final_df = final_df.loc[:, ~final_df.columns.duplicated()]
                    
                                    spread_ratio = final_df[(col_A, 'spread_ratio')] - final_df[(col_B, 'spread_ratio')]
                                    approx_price = final_df[(col_A, 'approx_price')] - final_df[(col_B, 'approx_price')]
                                    spread_value = final_df[(col_A, 'spread_value')] - final_df[(col_B, 'spread_value')]
                    
                                    # Ensure the subtraction results in Series and assign to spread_df
                                    spread_df[(f'{year}_spread', 'spread_ratio')] = spread_ratio.squeeze()
                                    spread_df[(f'{year}_spread', 'approx_price')] = approx_price.squeeze()
                                    spread_df[(f'{year}_spread', 'spread_value')] = spread_value.squeeze()
                    
                        elif abs(int(second_part_B) - int(second_part_A)) == 1:
                            # Different first parts, consecutive second parts
                            for i in range(len(unique_years) - 1):
                                year_A = unique_years[i]
                                year_B = unique_years[i + 1]
                    
                                col_A = f'{first_part_A}_{year_A}'
                                col_B = f'{first_part_B}_{year_B}'
                    
                                if col_A in final_df.columns.get_level_values(0) and col_B in final_df.columns.get_level_values(0):
                                    # Drop duplicate columns if any
                                    final_df = final_df.loc[:, ~final_df.columns.duplicated()].copy()
                    
                                    spread_ratio = final_df[(col_A, 'spread_ratio')] - final_df[(col_B, 'spread_ratio')]
                                    approx_price = final_df[(col_A, 'approx_price')] - final_df[(col_B, 'approx_price')]
                                    spread_value = final_df[(col_A, 'spread_value')] - final_df[(col_B, 'spread_value')]
                    
                                    # Ensure the subtraction results in Series and assign to spread_df
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'spread_ratio')] = spread_ratio.squeeze()
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'approx_price')] = approx_price.squeeze()
                                    spread_df[(f'{year_A}_vs_{year_B}_spread', 'spread_value')] = spread_value.squeeze()
                    
                        # Check if spread_df has columns before setting MultiIndex
                        if not spread_df.empty:
                            spread_df.columns = pd.MultiIndex.from_tuples(spread_df.columns)
                    
                        if spread_df.shape[1] > 0:
                            result_dict[key][subkey][comb] = spread_df.swaplevel(axis=1)
                    
                    else:
                        if final_df.shape[1] > 0:
                            # Store the final multiplied DataFrame in the result dict for non-tuple keys
                            result_dict[key][subkey][comb] = final_df.reindex(full_index).swaplevel(axis=1)

        return result_dict


    
    

    
    def seasonality_adj(self):
        filtered_dict = self.filter_and_process_combinations()
        current_contracts_dict = self.get_actual_contracts(filtered_dict)
        shifted_spread_ratios = self.process_and_shift_spread_ratios(filtered_dict)
        result_dict = self.combine_and_multiply(shifted_spread_ratios, current_contracts_dict)
        return result_dict

        

    
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
    params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1']*6
    params_dict['market_list'] = ['de'] * 6 + ['fr'] * 6 + ['hu'] * 6
    params_dict['delivery_list'] = ['base']*3 + ['peak'] * 3 +['base']*3 + ['peak'] * 3 + ['base']*3 + ['peak'] * 3
    params_dict['eD'] = dt.datetime(2024,8,9)  
    
    params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1', 'Y_2']*4
    params_dict['market_list'] = ['de'] * 8 + ['fr']*8
    params_dict['delivery_list'] = ['base']*4 + ['peak'] * 4 + ['base']*4 + ['peak'] * 4
    params_dict['eD'] = dt.datetime(2024,8,9)  
    
    fdc = FuturesDataCollector(params_dict)  
    raw_data = fdc.get_data_from_database()    
    fdp = FuturesDataProcessor(params_dict, raw_data)    
    spread_data_dict = fdp.create_spreads()
    
    fda = FuturesDataAnalyzer(params_dict, spread_data_dict)
    
    seas_df = fda.seasonality_adj()
    
    # # bb_dict = fda.bollinger_bands(kalman=False)
    # filtered_dict = fda.filter_and_process_combinations()
    # current_contracts_dict = fda.process_act_contracts(filtered_dict)
    # shifted_spread_ratios = fda.process_and_shift_spread_ratios(filtered_dict)
    # fda.combine_and_multiply(shifted_spread_ratios, current_contracts_dict)
        
        
        
        
        
    