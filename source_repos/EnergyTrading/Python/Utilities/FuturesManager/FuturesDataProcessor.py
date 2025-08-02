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

from functools import wraps
from itertools import combinations
import itertools
from collections import defaultdict


"""
    Class for processing raw data
    Input:
        params_dict
        raw_data from FuturesDataCollector
    
    Output:
        out_data_dict:
            spreads:
                calendar
                country
                base_peak
                css

"""

def update_dict_attributes(*attributes):
    """
    A decorator to update individual dictionary attributes of a class.
    
    Parameters:
    - attributes: A list of attribute names (dictionaries) to be updated.
    """
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            # Call the original method and get the new values
            result = method(self, *args, **kwargs)
            
            # Update each specified attribute with the new values
            for attr in attributes:
                if attr in kwargs:
                    if hasattr(self, attr):
                        attr_dict = getattr(self, attr)
                        if isinstance(attr_dict, dict):
                            attr_dict.update(kwargs[attr])
                        else:
                            raise TypeError(f"Attribute '{attr}' is not a dictionary.")
                    else:
                        raise AttributeError(f"Class has no attribute '{attr}'.")
            
            return result
        return wrapper
    return decorator


class FuturesDataProcessor:
    
    def __init__(self, params_dict: dict,
                raw_data_dict: dict):
        self._params_dict = params_dict
        self._raw_data_dict = raw_data_dict
        self._work_dict = {}
        
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def raw_data_dict(self):
        return self._raw_data_dict
    
    @update_dict_attributes('_raw_data_dict', '_work_dict')
    def update_dicts(self, **kwargs):
        # This method can be used to update dictionaries individually
        return kwargs
        
    
    @property
    def work_dict(self):
        return self._work_dict
    
    @property
    def prod_type_mapping(self):
        period_type_mapping = {
            'M': 'Month',
            'Q': 'Quarter',
            'Y': 'Year',
            'S': 'Season',
            'W': 'Week',
            'WKND': 'Weekend',
            'D': 'Day',
            'DEC': 'Dec'
        }
        return period_type_mapping
    @property
    def prod_type_map_reversed(self):

        reversed_mapping = {value: key for key, value in self.prod_type_mapping.items()}
        return reversed_mapping
    
    
    """
    Format of the contract names:
        'A_B_C_D_E':
            A - market name (e.g. 'DE', 'TTF', 'EUA')
            B - delivery (e.g. B for 'base')
            C - product (e.g. 'M' for month, 'Y' for year, 'DEC' for EUA December contacts)
            D - tenor (int of product number)
            E - year (last two digits of year)
    """
    
    # Insert contract names with the desired format
    
    def contract_name_creator(self, market_name, del_start, prod_type, delivery_name):
        # Check for NaN, NaT, or invalid delivery name
        if (
            pd.isna(market_name) or 
            pd.isna(del_start) or 
            pd.isna(prod_type) or 
            pd.isna(delivery_name) or 
            delivery_name[0] not in ['B', 'P']
        ):
            return float('nan')  # Return NaN if any value is missing

        market = market_name.upper()
        delivery = delivery_name[0]
        product = self.prod_type_map_reversed.get(prod_type)
        if product is None:
            return float('nan')  # Return NaN if prod_type is invalid

        if product in ['M', 'Q', 'S', 'Y']:
            if product != 'Q':
                tenor = del_start.month
            else:
                tenor = (del_start.month - 1) // 3 + 1
        elif product in ['W', 'WKND']:
            _, tenor, _ = del_start.isocalendar()
        elif product.upper() == 'DEC':
            tenor = 12
        else:
            tenor = del_start.strftime('%Y%m%d')
        
        year = str(del_start.year)[-2:]
        contract_name = f"{market}_{delivery}_{product}_{tenor}_{year}"
        return contract_name


    
    def insert_contract_names(self):
        raw_data_dict = deepcopy(self.raw_data_dict)
        
        for market, market_df in raw_data_dict.items():
            # Apply contract_name_creator to create the contract_name column
            market_df['contract_name'] = market_df.apply(
                lambda row: self.contract_name_creator(
                    market,
                    row['delivery_start'],
                    row['product_type'],
                    row['delivery']
                ),
                axis=1
            )
            
            # Filter out rows where contract_name is NaN
            market_df = market_df[market_df['contract_name'].notna()]
            
            # Assign the filtered DataFrame back to the dictionary
            raw_data_dict[market] = market_df.copy()
        
        # Update the raw_data_dict with the filtered DataFrames
        self.update_dicts(_raw_data_dict=raw_data_dict)
        del raw_data_dict

    
    
    # Create work dictionary where each contract will be key with its data in df
    def create_work_dict(self):
        self.insert_contract_names()
        work_dict = {}
        for market, market_df in self.raw_data_dict.items():
            unique_contracts = market_df['contract_name'].unique()
            for contract in unique_contracts:
                work_dict[contract] = market_df.loc[market_df['contract_name']==contract].copy()
        
        self.update_dicts(_work_dict=work_dict)
        del work_dict
        
    
    @staticmethod
    def get_start_date(item):
        """
        Get the start date for a given contract.
    
        Args:
            item (str): Contract identifier, e.g., 'DE_B_M_1_25'.
    
        Returns:
            datetime: Start date for the contract.
        """
        import datetime as dt
        import pandas as pd
    
        # Parse the contract string
        _, delivery, period_type, period_value, year = item.split('_')
        year = int(year) + 2000  # Convert to four-digit year (assuming 21st century)
    
        if period_type in ['M', 'Q', 'Y']:  # Month, Quarter, Year
            month = int(period_value)
    
            # Determine the first day of the period
            start_date = dt.datetime(year, month, 1)
    
            # Adjust for Peak contracts: Start on the first business day
            if delivery == 'P':  # Peak
                start_date = pd.Timestamp(start_date) + pd.offsets.BDay(0)
                return start_date.to_pydatetime()
    
            return start_date
    
        elif period_type == 'W':  # Week
            week = int(period_value)
            # Calculate the first day of the year
            first_day_of_year = dt.datetime(year, 1, 1)
            # Calculate the start of the given week (ISO calendar week)
            start_of_week = first_day_of_year + dt.timedelta(weeks=week - 1)
            # Adjust to Monday of the given week
            return start_of_week - dt.timedelta(days=start_of_week.weekday())
    
        else:
            raise ValueError(f"Unknown period type: {period_type}")

        
    # Create all possible spreads
    # Create function to return spread contract combinantions with leg weights
    def get_contract_for_spreads(self, work_dict):
        # Output will be dict
        spread_contracts_dict = {}
        non_power_markets = ['ttf', 'eua']
        contracts = list(work_dict.keys())
        
        # Extract power contracts
        power_contracts = [a for a in contracts if a.split('_')[0].lower() not in non_power_markets]
        
        # Create contracts for css
        # Find gas contract
        gas_contracts = ['TTF_' + a.split('_', 1)[1] for a in power_contracts]
        gas_contracts = [a.replace('_P_', '_B_') for a in gas_contracts]
        
        # Find eua contracts
        eua_contracts = ['EUA_B_DEC_12_' + str(a[-1]) for a in [a.split('_') for a in power_contracts]]
        css_contracts = [a for a in zip(power_contracts, gas_contracts, eua_contracts)]
        css_weights = [(1, 2, 0.411) for a in range(len(css_contracts))]
        spread_contracts_dict['css'] = [css_contracts, css_weights]
        
        # Create country_spreads
        unique_markets = np.unique([a[0] for a in [a.split('_') for a in power_contracts]])
        
        # Generate all combinations
        def generate_pairs(array):
            return list(combinations(array, 2))
        
        market_combinations = generate_pairs(unique_markets)
        country_spread_contracts = []
        for market_pair in market_combinations:
            first_leg_contracts = [a for a in power_contracts if a.split('_')[0] == market_pair[0]]
            second_leg_contracts = [a for a in power_contracts if a.split('_')[0] == market_pair[1]]
            country_spread_contracts.append([(item1, item2) for item1 in first_leg_contracts
                                            for item2 in second_leg_contracts
                                            if item1.split('_', 1)[1] == item2.split('_', 1)[1]])
        spread_contracts_dict['country_spreads'] = [market_combinations, country_spread_contracts]
        
        # def get_start_date(item):
        #     _, delivery, period_type, period_value, year = item.split('_')
        #     year = int(year)
        
        #     if period_type in ['M', 'Q', 'Y']:  # Month
        #         month = int(period_value)
        #         return dt.datetime(year, month, 1)
            
        #     # elif period_type == 'Q':  # Quarter
        #     #     quarter = int(period_value)
        #     #     month = (quarter - 1) * 3 + 1
        #     #     return dt.datetime(year, month, 1)
            
        #     # elif period_type == 'Y':  # Year
        #     #     return dt.datetime(year, 1, 1)
            
        #     elif period_type == 'W':  # Week
        #         week = int(period_value)
        #         # Calculate the first day of the year
        #         first_day_of_year = dt.datetime(year, 1, 1)
        #         # Calculate the start of the given week (ISO calendar week)
        #         start_of_week = first_day_of_year + dt.timedelta(weeks=week - 1)
        #         # Adjust to Monday of the given week
        #         return start_of_week - dt.timedelta(days=start_of_week.weekday())
            
        #     else:
        #         raise ValueError(f"Unknown period type: {period_type}")
        
        # Get calendar spread contracts
        market_calendar_spreads = []
        for market in unique_markets:
            aux_list = [a for a in power_contracts if a.split('_')[0] == market]
            
            market_spreads = []
            for item1, item2 in itertools.combinations(aux_list, 2):
                # Extract the necessary parts of the contract names
                _, type1, _, month1, year1 = item1.split('_')
                _, type2, _, month2, year2 = item2.split('_')
                
                # Ensure both contracts are of the same type and within 18 months difference
                date1 = self.get_start_date(item1)
                date2 = self.get_start_date(item2)
                month_diff = abs((date1.year - date2.year) * 12 + date1.month - date2.month)
                
                if type1 == type2 and month_diff <= 25:
                    market_spreads.append((item1, item2))
            
            market_calendar_spreads.append(market_spreads)
        
        spread_contracts_dict['calendar_spreads'] = [list(unique_markets), market_calendar_spreads]
        
        # Get base_peak spread contracts
        base_peak_contracts = [(a, a.replace('_B_', '_P_')) for a in power_contracts if '_B_' in a]
        
        # Extract unique countries and organize contracts by country
        countries = sorted(set(a.split('_')[0] for a in power_contracts))
        contract_combinations = {country: [] for country in countries}
        
        # Organize the base-peak pairs by country
        for base, peak in base_peak_contracts:
            country = base.split('_')[0]
            contract_combinations[country].append((base, peak))
        
        # Convert the contract_combinations dictionary into the required list format
        result = [list(contract_combinations.keys()), list(contract_combinations.values())]
        
        spread_contracts_dict['base_peak_spreads'] = result
        
        spread_contracts_dict['outright_contracts'] = list(work_dict.keys())
        
        return spread_contracts_dict


    
    @property
    def spread_functions_mapping(self):
        function_mapping = {
            'outright_contracts': self.create_outright_contracts,
            'css': self.create_css,
            'country_spreads': self.create_country_spreads,
            'calendar_spreads': self.create_calendar_spreads,
            'base_peak_spreads': self.create_base_peak_spreads
            }
        return function_mapping
    
    # Base on spread_contracts_dict complete each spread type
    
    def create_spreads(self, selected_contracts_list):
        self.create_work_dict()
        # Insert code to create projected settlements for all queried Qs and Cals
        updated_work_dict = self.compute_projected_settlement(deepcopy(self.work_dict))
        filtered_work_dict = {a:b for a,b in deepcopy(updated_work_dict).items()
                            if a in selected_contracts_list}
        del updated_work_dict
        # Filter out contracts not queried based on params_dict
        spread_contracts_dict = self.get_contract_for_spreads(filtered_work_dict)
        spread_data_dict = {}
        for spread_type, spread_type_lists in spread_contracts_dict.items():
            pass
            spread_data_dict[spread_type] = self.spread_functions_mapping[spread_type](self.work_dict, spread_type_lists)
        return spread_data_dict
    
    def create_selected_spreads(self, spreads_list: list):
        if not self.work_dict:
            self.create_work_dict()
            
        """
        spreads_list example [['DE_B_M_2_25'],
                            ['DE_B_M_3_25']]
        is for spread de base spread de febXmar 2025
        """
        
        spreads_dict = {}
        hours_dict = {}
        
        for leg1_name, leg2_name in zip(spreads_list[0],
                                        spreads_list[1]):
            leg1 = self.work_dict[leg1_name].dropna().copy()
            leg2 = self.work_dict[leg2_name].dropna().copy()
            spread_hours = self.get_max_hours(leg1_name, leg2_name)
            spread_name = f"{leg1_name}x{leg2_name}"
            
            
            spread = pd.DataFrame(leg1['settlement_price']-leg2['settlement_price'])
            spreads_dict[spread_name] = spread.copy()
            hours_dict[spread_name] = spread_hours
        return spreads_dict, hours_dict
    

    def get_max_hours(self, leg1_name, leg2_name):
        leg1_hours = self.compute_contract_hours(leg1_name)
        leg2_hours = self.compute_contract_hours(leg2_name)
        
        hours = [leg1_hours,leg2_hours]
        
        ratio = round(max(hours)/min(hours))
        
        return max(max(hours),min(hours)*ratio)
    
    def compute_contract_hours(self, contract):
        """
        Compute the number of hours for a given contract.
    
        Args:
            contract (str): Contract identifier, e.g., 'DE_B_M_1_25'.
    
        Returns:
            int: Number of hours for the contract.
        """
        import calendar
    
        # Parse the contract details
        _, delivery, period_type, period_value, year = contract.split('_')
        year = int(year) + 2000  # Convert to four-digit year (assuming 21st century)
    
        # Get the start date
        start_date = self.get_start_date(contract)
    
        # Determine the end date based on the period type
        if period_type == 'M':  # Month
            month = int(period_value)
            _, days_in_month = calendar.monthrange(year, month)
            end_date = dt.datetime(year, month, days_in_month, 23, 59)
    
        elif period_type == 'Q':  # Quarter
            quarter_start_month = int(period_value)
            quarter_end_month = quarter_start_month + 2
            _, days_in_end_month = calendar.monthrange(year, quarter_end_month)
            end_date = dt.datetime(year, quarter_end_month, days_in_end_month, 23, 59)
    
        elif period_type == 'Y':  # Year
            end_date = dt.datetime(year, 12, 31, 23, 59)
    
        elif period_type == 'W':  # Week
            end_date = start_date + dt.timedelta(days=6, hours=23, minutes=59)
    
        else:
            raise ValueError(f"Unknown period type: {period_type}")
    
        # Calculate hours based on delivery type
        if delivery == 'B':  # Baseload: All hours in the period
            hours = int((end_date - start_date).total_seconds() // 3600) + 1
    
        elif delivery == 'P':  # Peak: Business-day hours (09:00 to 20:00 inclusive)
            # Generate the business days within the date range
            business_days = pd.date_range(start=start_date, end=end_date, freq='B')
            hours = len(business_days) * 12  # 12 hours per business day (09:00 to 20:00 inclusive)
    
        else:
            raise ValueError(f"Unknown delivery type: {delivery}")
    
        return hours
    
    # Method for including outright contracts to spreads
    def create_outright_contracts(self, work_dict, spread_type_list):
        outright_contracts_dict = {}
        for contract, contract_df in work_dict.items():
            market, del_type, prod_type, period, year = contract.split('_')
            
            if market not in outright_contracts_dict:
                outright_contracts_dict[market] = {}
            outright_contracts_dict[market][contract] = contract_df[['settlement_price']]
            
        return outright_contracts_dict
    
    # Method for creating css
    def create_css(self, work_dict, spread_type_lists):
        css_dict = {}
        for contracts, weights in zip(spread_type_lists[0], spread_type_lists[1]):
            css_list = []
            market, del_typ, prod_type, period, year = contracts[0].split('_')
            if market not in css_dict:
                css_dict[market] = {}
            for contract, weight in zip(contracts, weights):
                
                aux = work_dict[contract].copy()
                
                # Check for duplicates in the index and drop them
                if not aux.index.is_unique:
                    print(f"DataFrame for contract {contract} has duplicated index values.")
                    aux = aux[~aux.index.duplicated(keep='first')]  # Drop duplicate indices
                
                # Modify the level 0 column names to include the contract name
                aux.columns = pd.MultiIndex.from_product([[contract], aux.columns])
                
                css_list.append(aux)
            
            # Concatenate the DataFrames
            try:
                concatenated_df = pd.concat(css_list, axis=1, join='inner')
                
                # Extract 'settlement_price', 'open_interest_lots', and 'traded_lots' columns from the first DataFrame
                settlement_price_1 = concatenated_df[(contracts[0], 'settlement_price')]
                settlement_price_2 = concatenated_df[(contracts[1], 'settlement_price')]
                settlement_price_3 = concatenated_df[(contracts[2], 'settlement_price')]
                
                open_interest_lots = concatenated_df[(contracts[0], 'open_interest_lots')]
                traded_lots = concatenated_df[(contracts[0], 'traded_lots')]
                
                # Calculate the weighted difference for 'css'
                css_settlement_price = (weights[0] * settlement_price_1 
                                        - weights[1] * settlement_price_2 
                                        - weights[2] * settlement_price_3)
                
                # Calculate the 'ghr' ratio
                ghr_ratio = settlement_price_1 / (settlement_price_2 + 0.2 * settlement_price_3)
                
                # Create a new DataFrame for 'css' and 'ghr'
                css_ghr_df = pd.DataFrame({
                    ('css', 'spread_value'): css_settlement_price,
                    ('css', 'open_interest_lots'): open_interest_lots,
                    ('css', 'traded_lots'): traded_lots,
                    ('css', 'spread_ratio'): ghr_ratio
                })
                
                # Concatenate css_ghr_df with the rest of the concatenated DataFrame
                concatenated_df = pd.concat([css_ghr_df, concatenated_df], axis=1)
                
                # Reorder the columns to move all 'css' and 'ghr' columns to the front
                # First, extract the css and ghr columns
                css_columns = concatenated_df.loc[:, 'css'].columns.tolist()
                # ghr_columns = concatenated_df.loc[:, 'ghr'].columns.tolist()
                
                # Create the new column order
                new_column_order = (pd.MultiIndex.from_tuples([('css', col) for col in css_columns] +
                                                            [col for col in concatenated_df.columns 
                                                            if col[0] not in ['css']]))
                
                # Reindex the DataFrame to apply the new order
                concatenated_df = concatenated_df.reindex(columns=new_column_order)
                
                # Update css_dict with the newly created DataFrame
                css_dict[market][contracts[0]] = concatenated_df
            
            except pd.errors.InvalidIndexError as e:
                print(f"Error during concatenation for contracts: {contracts}")
                for i, df in enumerate(css_list):
                    print(f"DataFrame {i} index:\n{df.index}")
                    print(f"DataFrame {i} columns:\n{df.columns}")
                raise e
        return css_dict

    # Method for creating calendar_spread
    def create_country_spreads(self, work_dict, spread_type_lists):
        country_spread_dict = {}
        
        # Iterate over the country combinations and their corresponding contract combinations
        for country_pair, contract_pairs_list in zip(spread_type_lists[0], spread_type_lists[1]):
            contract_spread_dict = {}
            
            # Iterate over each contract pair within the country pair
            for contract_pair in contract_pairs_list:
                contract_1, contract_2 = contract_pair
                
                # Retrieve the relevant DataFrames from work_dict
                df_1 = work_dict[contract_1].copy()
                df_2 = work_dict[contract_2].copy()
                
                # Check for duplicates in the index and drop them
                if not df_1.index.is_unique:
                    print(f"DataFrame for contract {contract_1} has duplicated index values.")
                    df_1 = df_1[~df_1.index.duplicated(keep='first')]
                
                if not df_2.index.is_unique:
                    print(f"DataFrame for contract {contract_2} has duplicated index values.")
                    df_2 = df_2[~df_2.index.duplicated(keep='first')]
                
                # Modify the level 0 column names to include the contract names
                df_1.columns = pd.MultiIndex.from_product([[contract_1], df_1.columns])
                df_2.columns = pd.MultiIndex.from_product([[contract_2], df_2.columns])
                
                # Concatenate the two DataFrames along columns
                concatenated_df = pd.concat([df_1, df_2], axis=1, join='inner')
                
                # Calculate the country spread and ratio
                country_spread = concatenated_df[(contract_1, 'settlement_price')] - concatenated_df[(contract_2, 'settlement_price')]
                ratio = concatenated_df[(contract_1, 'settlement_price')] / concatenated_df[(contract_2, 'settlement_price')]
                
                # Create a new DataFrame for 'country_spreads' and 'ratio'
                spread_df = pd.DataFrame({
                    ('country_spreads', 'spread_value'): country_spread,
                    ('country_spreads', 'spread_ratio'): ratio
                }, index=concatenated_df.index)
                
                # Concatenate spread_df with the original concatenated DataFrame
                full_df = pd.concat([spread_df, concatenated_df], axis=1)
                
                # Reorder the columns to move 'country_spreads' columns to the front
                spread_columns = spread_df.columns.tolist()
                other_columns = [col for col in full_df.columns if col not in spread_columns]
                
                new_column_order = spread_columns + other_columns
                
                full_df = full_df.reindex(columns=new_column_order)
                
                # Add the resulting DataFrame to the contract_spread_dict under the contract pair key
                contract_spread_dict[contract_pair] = full_df
            
            # Add the contract_spread_dict to the country_spread_dict under the country pair key
            country_spread_dict[country_pair] = contract_spread_dict
        
        return country_spread_dict



    
    
    
    # Method for creating country_spread
    def create_calendar_spreads(self, work_dict, spread_type_lists):
        calendar_spread_dict = {}
        
        # Iterate over the countries and their corresponding contract combinations
        for country, contract_pairs_list in zip(spread_type_lists[0], spread_type_lists[1]):
            contract_spread_dict = {}
            
            # Iterate over each contract pair within the country
            for contract_pair in contract_pairs_list:
                contract_1, contract_2 = contract_pair
                
                # Retrieve the relevant DataFrames from work_dict
                df_1 = work_dict[contract_1].copy()
                df_2 = work_dict[contract_2].copy()
                
                # Check for duplicates in the index and drop them
                if not df_1.index.is_unique:
                    print(f"DataFrame for contract {contract_1} has duplicated index values.")
                    df_1 = df_1[~df_1.index.duplicated(keep='first')]
                
                if not df_2.index.is_unique:
                    print(f"DataFrame for contract {contract_2} has duplicated index values.")
                    df_2 = df_2[~df_2.index.duplicated(keep='first')]
                
                # Modify the level 0 column names to include the contract names
                df_1.columns = pd.MultiIndex.from_product([[contract_1], df_1.columns])
                df_2.columns = pd.MultiIndex.from_product([[contract_2], df_2.columns])
                
                # Concatenate the two DataFrames along columns
                concatenated_df = pd.concat([df_1, df_2], axis=1, join='inner')
                
                # Calculate the calendar spread and ratio
                calendar_spread = concatenated_df[(contract_1, 'settlement_price')] - concatenated_df[(contract_2, 'settlement_price')]
                ratio = concatenated_df[(contract_1, 'settlement_price')] / concatenated_df[(contract_2, 'settlement_price')]
                
                # Create a new DataFrame for 'calendar_spread' and 'ratio'
                spread_df = pd.DataFrame({
                    ('calendar_spreads', 'spread_value'): calendar_spread,
                    ('calendar_spreads', 'spread_ratio'): ratio
                }, index=concatenated_df.index)
                
                # Concatenate spread_df with the original concatenated DataFrame
                full_df = pd.concat([spread_df, concatenated_df], axis=1)
                
                # Reorder the columns to move 'calendar_spread' columns to the front
                spread_columns = spread_df.columns.tolist()
                other_columns = [col for col in full_df.columns if col not in spread_columns]
                
                new_column_order = spread_columns + other_columns
                
                full_df = full_df.reindex(columns=new_column_order)
                if len(full_df)>0:                
                    # Add the resulting DataFrame to the contract_spread_dict under the contract pair key
                    contract_spread_dict[contract_pair] = full_df
            
            # Add the contract_spread_dict to the calendar_spread_dict under the country key
            calendar_spread_dict[country] = contract_spread_dict
        
        return calendar_spread_dict


    
    # Method for creating base_peak_spread
    def create_base_peak_spreads(self, work_dict, base_peak_spread_lists):
        base_peak_spread_dict = {}
        
        # Extract the list of countries and their corresponding contract combinations
        countries, contract_combinations = base_peak_spread_lists
        
        # Iterate over the countries and their corresponding contract combinations
        for country, contracts_list in zip(countries, contract_combinations):
            country_spread_dict = {}
            
            # Iterate over each contract pair within the country
            for base_contract, peak_contract in contracts_list:
                
                # Retrieve the relevant DataFrames from work_dict
                df_base = work_dict[base_contract].copy()
                df_peak = work_dict[peak_contract].copy()
                
                # Check for duplicates in the index and drop them
                if not df_base.index.is_unique:
                    print(f"DataFrame for contract {base_contract} has duplicated index values.")
                    df_base = df_base[~df_base.index.duplicated(keep='first')]
                
                if not df_peak.index.is_unique:
                    print(f"DataFrame for contract {peak_contract} has duplicated index values.")
                    df_peak = df_peak[~df_peak.index.duplicated(keep='first')]
                
                # Modify the level 0 column names to include the contract names
                df_base.columns = pd.MultiIndex.from_product([[base_contract], df_base.columns])
                df_peak.columns = pd.MultiIndex.from_product([[peak_contract], df_peak.columns])
                
                # Concatenate the two DataFrames along columns
                concatenated_df = pd.concat([df_base, df_peak], axis=1, join='inner')
                
                # Calculate the base-peak spread and ratio
                base_peak_spread = concatenated_df[(base_contract, 'settlement_price')] - concatenated_df[(peak_contract, 'settlement_price')]
                ratio = concatenated_df[(base_contract, 'settlement_price')] / concatenated_df[(peak_contract, 'settlement_price')]
                
                # Create a new DataFrame for 'base_peak_spread' and 'ratio'
                spread_df = pd.DataFrame({
                    ('base_peak_spreads', 'spread_value'): base_peak_spread,
                    ('base_peak_spreads', 'spread_ratio'): ratio
                }, index=concatenated_df.index)
                
                # Concatenate spread_df with the original concatenated DataFrame
                full_df = pd.concat([spread_df, concatenated_df], axis=1)
                
                # Reorder the columns to move 'base_peak_spread' columns to the front
                spread_columns = spread_df.columns.tolist()
                other_columns = [col for col in full_df.columns if col not in spread_columns]
                
                new_column_order = spread_columns + other_columns
                
                full_df = full_df.reindex(columns=new_column_order)
                
                # Add the resulting DataFrame to the country_spread_dict under the contract pair key
                country_spread_dict[(base_contract, peak_contract)] = full_df
                    

            
            # Add the country_spread_dict to the base_peak_spread_dict under the country key
            base_peak_spread_dict[country] = country_spread_dict
        
        return base_peak_spread_dict
    

    def compute_projected_settlement(self, contract_dict):
        projected_settlements = {}
        
        updated_contract_dict = deepcopy(contract_dict)

        # Filter out invalid contract names
        contract_dict = {k: v for k, v in contract_dict.items() if 'nan' not in k.lower() and 'na' not in k.lower()}

        for contract_name, df in contract_dict.items():
            # Parse contract details from its name
            parts = contract_name.split("_")
            market, delivery_type, product_type, period, year = parts[0], parts[1], parts[2], int(parts[3]), int(parts[4]) + 2000

            if product_type == "M":
                continue  # Skip monthly contracts

            # Determine the contract's time axis (all months during its duration)
            if product_type == "Q":
                start_month = (period - 1) * 3 + 1
                end_month = start_month + 2
            elif product_type == "S":
                start_month = 4 if period == 1 else 10
                end_month = 9 if period == 1 else 3
            elif product_type == "Y":
                start_month = 1
                end_month = 12
            else:
                continue  # Unsupported product type

            start_date = dt.datetime(year, start_month, 1)
            if contract_dict['DE_B_Y_1_'+str(dt.datetime.now().year+1)[-2:]].index.max() < start_date:
                continue
            end_date = (pd.Timestamp(year, end_month, 1) + pd.offsets.MonthEnd(0)).date()
            months_range = pd.date_range(start=start_date, end=end_date, freq='MS')
            # Mapping: Identify relevant subcontracts (monthly and quarterly)
            mapping = {}
            for current_month in months_range:
                if current_month > dt.datetime.now():
                    continue
                # Get the last day of the quarter that the target_month belongs to
                quarter_start_month = ((current_month.month - 1) // 3) * 3 + 1
                quarter_end = pd.Timestamp(current_month.year, quarter_start_month, 1) + pd.offsets.QuarterEnd(0)
                
                # target_months_range = self.get_target_months(current_month)
                for target_month in months_range:
                    if target_month < current_month:
                        # Past months: Use the last available price
                        month_contract = f"{market}_{delivery_type}_M_{target_month.month}_{target_month.year % 100}"
                        hours = self.compute_hours('M', target_month.year % 100, target_month.month, delivery_type)
                        if month_contract in contract_dict:
                            month_df = contract_dict[month_contract].reset_index()
                            month_df = month_df.loc[~month_df.duplicated(subset=['datetime', 'settlement_price'], keep='first')].set_index('datetime')
                            month_df = month_df.groupby(month_df.index).first()
                            if not month_df.empty:
                                last_price = month_df['settlement_price'].iloc[[-1]]
                                mapping[month_contract] = (last_price, 'M', hours)
                    elif target_month <= quarter_end:
                        # Current or future months within the quarter: Use monthly contracts
                        month_contract = f"{market}_{delivery_type}_M_{target_month.month}_{target_month.year % 100}"
                        hours = self.compute_hours('M', target_month.year % 100, target_month.month, delivery_type)
                        if month_contract in contract_dict:
                            month_df = contract_dict[month_contract].reset_index()
                            month_df = month_df.loc[~month_df.duplicated(subset=['datetime','settlement_price'], keep='first')].set_index('datetime')
                            month_df = month_df.groupby(month_df.index).first()
                            mapping[month_contract] = (month_df.loc[current_month:current_month + pd.offsets.MonthEnd(0), 'settlement_price'],
                                                        'M', hours)
                    else:
                        # Use quarterly contracts for months beyond the current quarter
                        quarter = (target_month.month - 1) // 3 + 1
                        hours = self.compute_hours('Q', target_month.year % 100, quarter, delivery_type)
                        quarter_contract = f"{market}_{delivery_type}_Q_{quarter}_{target_month.year % 100}"
                        if quarter_contract in contract_dict:
                            try:
                                quarter_df = contract_dict[month_contract].reset_index()
                            except:
                                print('833')
                            quarter_df = quarter_df.loc[~quarter_df.duplicated(subset=['datetime','settlement_price'], keep='first')].set_index('datetime')
                            quarter_df = quarter_df.groupby(quarter_df.index).first()
                            mapping[quarter_contract] = (quarter_df.loc[current_month:current_month + pd.offsets.MonthEnd(0), 'settlement_price'],
                                                    'Q', hours)
                    # Compute weighted average price for the month
                    
                    # Ensure that the index in each DataFrame in mapping.values() is unique
                    for key, a in mapping.items():
                        assert a[0].index.is_unique, f"Index in mapping for key '{key}' is not unique."

                    # Proceed with the concatenation
                    combined_data = pd.concat([a[0] for a in mapping.values()], axis=1, keys=list(mapping.keys())).ffill().dropna()
                    weights = [a[-1] for a in mapping.values()]
                    contract_series = pd.Series((combined_data * weights).sum(axis=1)/sum(weights),
                                                name='settlement_price')
                    projected_settlement_column = pd.DataFrame(contract_series)
                    # Add columns to contract_dict
                    completed_df = pd.concat([updated_contract_dict[contract_name],
                                                                    projected_settlement_column]).ffill()
                    completed_df = completed_df.reset_index().drop_duplicates().set_index('datetime')
                    updated_contract_dict[contract_name] = completed_df.copy()
                    del completed_df

        return updated_contract_dict

    @staticmethod
    def compute_hours(product_type, year_abv, period, delivery_type):
        """
        Computes the total number of hours for a given product type, period, and delivery type.
        
        Parameters:
            product_type (str): The type of product ('M', 'Q', 'S', 'Y').
            year (int): The year of the product.
            period (int): The period (1-12 for 'M', 1-4 for 'Q', etc.).
            delivery_type (str): The delivery type ('B' for Base, 'P' for Peak).
        
        Returns:
            int: The total number of hours.
        """
        def get_month_days(year, month):
            return pd.Period(f"{year}-{month:02}").days_in_month

        def business_days_in_month(year, month):
            start_date = pd.Timestamp(year, month, 1)
            end_date = pd.Timestamp(year, month, get_month_days(year, month))
            return pd.bdate_range(start=start_date, end=end_date).size

        total_hours = 0
        
        year = 2000 + int(year_abv)

        if product_type == "M":
            # Monthly product
            if delivery_type == "B":
                total_hours = get_month_days(year, period) * 24
            elif delivery_type == "P":
                total_hours = business_days_in_month(year, period) * 12

        elif product_type == "Q":
            # Quarterly product
            start_month = (period - 1) * 3 + 1
            end_month = start_month + 2
            for month in range(start_month, end_month + 1):
                if delivery_type == "B":
                    total_hours += get_month_days(year, month) * 24
                elif delivery_type == "P":
                    total_hours += business_days_in_month(year, month) * 12

        elif product_type == "S":
            # Seasonal product
            if period == 1:  # Summer (April to September)
                months = range(4, 10)
            elif period == 2:  # Winter (October to March)
                months = list(range(10, 13)) + list(range(1, 4))
            else:
                raise ValueError("Invalid period for Seasonal product.")

            for month in months:
                if month > 12:  # Handle December to January wrap
                    adjusted_year = year + 1
                    adjusted_month = month - 12
                else:
                    adjusted_year = year
                    adjusted_month = month

                if delivery_type == "B":
                    total_hours += get_month_days(adjusted_year, adjusted_month) * 24
                elif delivery_type == "P":
                    total_hours += business_days_in_month(adjusted_year, adjusted_month) * 12

        elif product_type == "Y":
            # Yearly product
            for month in range(1, 13):
                if delivery_type == "B":
                    total_hours += get_month_days(year, month) * 24
                elif delivery_type == "P":
                    total_hours += business_days_in_month(year, month) * 12

        else:
            raise ValueError("Unsupported product type.")

        return total_hours
    
    @staticmethod
    def get_target_months(current_month):
        """
        Get a list of target months based on the current month.
        
        Parameters:
            current_month (int): The current month (1 to 12).
            
        Returns:
            List[str]: A list of target months as strings in 'YYYY-MM-DD' format.
        """
        # Determine the year and quarter of the current month
        year = pd.Timestamp.now().year
        quarter = (current_month - 1) // 3 + 1

        # Define quarters as a dictionary
        quarters = {
            1: [1, 2, 3],
            2: [4, 5, 6],
            3: [7, 8, 9],
            4: [10, 11, 12]
        }

        # Collect all months up to the current quarter
        target_months = []
        for q in range(1, quarter + 1):
            target_months.extend(quarters[q])
        
        # Add start months of future quarters
        for q in range(quarter + 1, 5):
            target_months.append(quarters[q][0])  # Only the start month of the quarter

        # Convert months to start-of-month dates
        target_dates = [pd.Timestamp(year, month, 1).strftime('%Y-%m-%d') for month in target_months]
        
        return target_dates





        
if __name__== '__main__':
    params_dict = {}
    params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1']*6
    params_dict['market_list'] = ['de'] * 6 + ['fr'] * 6 + ['hu'] * 6
    params_dict['delivery_list'] = ['base']*3 + ['peak'] * 3 +['base']*3 + ['peak'] * 3 + ['base']*3 + ['peak'] * 3
    params_dict['eD'] = dt.datetime(2024,11,6)   
    
    fdc = FuturesDataCollector(params_dict)
    
  
    raw_data = fdc.get_data_from_database()
    
    fdp = FuturesDataProcessor(params_dict, raw_data)
    
    spread_dict = fdp.create_spreads()
        
        
        
        
        
    