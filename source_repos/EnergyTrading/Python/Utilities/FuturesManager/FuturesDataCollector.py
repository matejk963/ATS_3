# -*- coding: utf-8 -*-
"""
Created on Sat Aug 10 16:30:52 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
from copy import deepcopy
from dateutil.relativedelta import relativedelta

from Database.DB_reader import Database


"""
    Class for collecting data from source
    Main source for power, gas and eua will be Database
    Eikon will be used for coal or as backup, cola will be moved to Database
    
    In future ICE contracts whould be available directly
"""


class FuturesDataCollector:
    def __init__(self, params_dict: dict):
        self._params_dict = params_dict
        
            
    @property
    def params_dict(self):
        return self._params_dict
    
    #  product_type mapping dict
    @property
    def prod_type_map(self):
        period_type_mapping = {
        'M': 'Month',
        'Q': 'Quarter',
        'Y': 'Year',
        'S': 'Season',
        'W': 'Week',
        'WKND': 'Weekend',
        'D': 'Day'
        }
        return period_type_mapping
    
    #  delivery_start date offset mapping
    # Each with its distinct period
    @property
    def del_start_offset(self):
        delivery_start_offset_mapping = {
            'M': 1,
            'Q': 3,
            'Y': 12,
            'S': 6,
            'W': 7,
            'WKND': 5,
            'D': 1
            }
        return delivery_start_offset_mapping
    
    @property
    def query_methods(self):
        """
        Property that returns a dictionary mapping keys to query builder methods.
        """
        return {
            "all": self.build_sql_queries_for_product_types,
            "selected": self.build_sql_queries_from_groupped_list
        }
        
    # Main objective is to collect data
    # From Database I need to know
    #  product_type (month, week, year...)
    #  pelivery_start (datetime)
    
    # First extract these variables from params_dict
    #  product_type
    def get_product_type_list(self, params_dict:dict = None):
        if params_dict is None:
            params_dict = deepcopy(self.params_dict)
        product_types_list = [self.prod_type_map.get(a.split('_')[0])
                         for a in params_dict['product_list']]
        # delete params_dict to free up the memory
        del params_dict
        return product_types_list
    # delivery_start
    def get_delivery_start_list(self, params_dict:dict = None):
        if params_dict is None:
            params_dict = deepcopy(self.params_dict)
        delivery_start_list = []
        for product in params_dict['product_list']:
            prod_type, time_shift = product.split('_')
            time_shift = int(time_shift)
            if prod_type.upper() in ['M', 'Q', 'S', 'Y']:
                del_start = params_dict['eD'] + pd.DateOffset(months=
                                                              (time_shift*self.del_start_offset.get(prod_type)))
                if prod_type.upper() in ['Y']:
                    del_start = del_start.replace(month=1, day=1)
                elif prod_type.upper() in ['S']:
                    if 4 <= del_start.month <= 9:
                        del_start = del_start.replace(month=4, day=1)
                    elif 10 <= del_start.month <=12:
                        del_start = del_start.replace(months=10, day=1)
                    else:
                        del_start = (del_start - relativedelta(years=1)).replace(month=10, day=1)
                elif prod_type.upper() in ['Q']:
                    del_start = del_start.replace(month=(((del_start.month - 1) // 3) * 3 + 1),
                                                  day=1)
                else:
                    del_start = del_start.replace(day=1)
            elif prod_type.upper() in ['W']:
                del_start = params_dict['eD'] + dt.timedelta(days=(time_shift*
                                                                   self.del_start_offset.get(prod_type)-
                                                                   params_dict['eD'].weekday()))
            elif prod_type.upper() in ['WKND']:
                del_start = params_dict['eD'] + dt.timedelta(days=((time_shift-1)*7+
                                                                   self.del_start_offset.get(prod_type)-
                                                                   params_dict['eD'].weekday()))
            elif prod_type.upper() in ['D']:
                del_start = params_dict['eD'] + dt.timedelta(days=(time_shift*
                                                                   self.del_start_offset.get(prod_type)))
                
                
            delivery_start_list.append(del_start)
            del del_start       
        
        # delete params_dict to free up the memory
        del params_dict
        return delivery_start_list
    
    
    # Group elements with their respective market
    def group_params_on_markets(self):
        def sort_and_align_lists(*lists):
            # Ensure there is at least one list to sort by
            if not lists or len(lists) < 1:
                raise ValueError("At least one list is required")
        
            # Combine the lists into a list of tuples
            combined = list(zip(*lists))
            
            # Sort the combined list based on the first list
            combined_sorted = sorted(combined, key=lambda x: x[0])
            
            # Unzip the sorted combined list
            sorted_lists = list(zip(*combined_sorted))
            
            return [list(sorted_list) for sorted_list in sorted_lists]
        params_dict = deepcopy(self.params_dict)
        # Align based on sorted markets lists
        
        # State all lists to be work with
        product_type_list = self.get_product_type_list(params_dict)
        delivery_start_list = self.get_delivery_start_list(params_dict)
        market_list = params_dict['market_list']
        delivery_list = params_dict['delivery_list']
        
        # Extent params for fuels contracts
        market_list,\
            product_type_list,\
                delivery_start_list,\
                    delivery_list = self.extend_params_for_fuels(product_type_list, delivery_start_list,
                                                market_list, delivery_list)
        
        # Extend history
        market_list,\
            product_type_list,\
                delivery_start_list,\
                    delivery_list= self.extend_history(market_list,
                                                        product_type_list,
                                                        delivery_start_list,
                                                        delivery_list)
        # Sort and align by markets
        market_list,\
            product_type_list,\
                delivery_start_list,\
                    delivery_list= sort_and_align_lists(market_list,
                                                        product_type_list,
                                                        delivery_start_list,
                                                        delivery_list)
        
        market_out = np.unique(market_list, return_index=True)
        indices = np.append(market_out[1], len(product_type_list))
        product_unique_lists = [product_type_list[market_index:indices[i+1]] for
                               i, market_index in enumerate(indices[:-1])]
        delivery_start_unique_lists = [delivery_start_list[market_index:indices[i+1]] for
                               i, market_index in enumerate(indices[:-1])]
        delivery_type_unique_lists = [delivery_list[market_index:indices[i+1]] for
                               i, market_index in enumerate(indices[:-1])]
        market_unique_lists = [str(a) for a in market_out[0]]
        del params_dict
        
        return market_unique_lists,\
                delivery_start_unique_lists,\
                delivery_type_unique_lists,\
                    product_unique_lists
                    
    # Extend the params lists to include history up to 2019
    @staticmethod
    def extend_history(market_list,
                       product_type_list,
                       delivery_start_list,
                       delivery_list):
        # Initialize empty lists to store the extended results
        extended_market_list = market_list
        extended_product_type_list = product_type_list
        extended_delivery_start_list = delivery_start_list
        extended_delivery_list = delivery_list
    
        # Iterate through each quartet of elements using list comprehension
        for market, product_type, delivery_start, delivery in zip(market_list, product_type_list, delivery_start_list, delivery_list):
            # Shift the delivery_start date back by 1 year or 52 weeks until it reaches 2019 or before
            while delivery_start.year >= 2019:
                # Determine the shift amount
                if 'Dec' in product_type or any(x in product_type for x in ['M', 'Q', 'S', 'Y']):
                    delivery_start = delivery_start - relativedelta(years=1)  # Shift by 12 months
                else:
                    delivery_start = delivery_start - relativedelta(weeks=52)  # Shift by 52 weeks
    
                # Skip if the date is January 2019
                if delivery_start.year == 2019 and delivery_start.month == 1:
                    break
    
                # Append the current state of the quartet to the extended lists
                extended_market_list.append(market)
                extended_product_type_list.append(product_type)
                extended_delivery_start_list.append(delivery_start)
                extended_delivery_list.append(delivery)
    
                # If delivery_start has reached exactly 2019 (but not January), include it in the result
                if delivery_start.year == 2019:
                    break
    
        return extended_market_list,\
            extended_product_type_list,\
            extended_delivery_start_list,\
            extended_delivery_list

                    
    # Extend the params_list for gas, coal and eua contracts
    # Gas, eua for now
    @staticmethod
    def extend_params_for_fuels(product_type_list, delivery_start_list,
                                market_list, delivery_list):
        # Gas will have the same product_list
        # Delivery will be only 'base'
        gas_product_type_list = [a for a in product_type_list]
        gas_delivery_start_list = [a for a in delivery_start_list]
        # Here specify the gas for each market
        # To be inplemented, TTF for all
        gas_name_list = ['ttf' for a in market_list]
        gas_delivery_list = ['Base' for a in delivery_list]
        
        # EUA will have 'base' as delivery type
        # 'Year' as product type
        # First of December of given for each delivery start
        eua_product_type_list = ['Dec' for a in product_type_list]
        eua_delivery_start_list = [dt.datetime(a.year,12,1)
                                   if a<dt.datetime(a.year,12,1)
                                   else dt.datetime(a.year+1,12,1)
                                   for a in delivery_start_list]
        eua_name_list = ['eua' for a in market_list]
        eua_delivery_list = ['base' for a in delivery_list]
        
        market_list.extend(gas_name_list + eua_name_list)
        product_type_list.extend(gas_product_type_list + eua_product_type_list)
        delivery_start_list.extend(gas_delivery_start_list + eua_delivery_start_list)
        delivery_list.extend(gas_delivery_list + eua_delivery_list)
        
        # Remove Jan 2019 from contracts as they have insufficient data history in database
        elements_to_remove = [dt.datetime(2019,1,1)]
        indices_to_remove = [i for i, element in enumerate(delivery_start_list)
                             if element in elements_to_remove]
        indices_to_remove.sort(reverse=True)
        for index in indices_to_remove:
            del market_list[index]
            del product_type_list[index]
            del delivery_start_list[index]
            del delivery_list[index]
        
        
        
        return market_list,\
            product_type_list,\
                delivery_start_list,\
                    delivery_list
        
        
                    
                    
    # Extract the data from database
    def get_data_from_database(self, query_type: str = 'all',
                               columns_to_keep: list = None):
        if columns_to_keep is None:
            columns_to_keep = ['datetime', 'delivery_start', 'delivery_end',
                                'product_type', 'settlement_price',
                                'open_interest_lots', 'traded_lots',
                                'lot_size', 'delivery']
        params_dict = deepcopy(self.params_dict)
        grouped_lists = self.group_params_on_markets()
        # Insert here code to get contract codes from grouped lists
        selected_contracts_list = self.generate_contracts(grouped_lists)
        # This will serve as the filter for selecting contracts to create projected settlement for
        schema_name = 'futures'
        
        sql_queries =self.query_methods.get(query_type)(schema_name, grouped_lists)
        db = Database()
        raw_data_dict = {}
        for market, sql_query in zip(grouped_lists[0],
                                     sql_queries):
            raw_data_aux = db.execute(sql_query)
            raw_data_dict[market] = raw_data_aux
        
        # Select desired columns
        out_data_dict = self._clean_raw_database_data(raw_data_dict, columns_to_keep)
        return out_data_dict, selected_contracts_list
    
    # @staticmethod
    # def _clean_raw_database_data(raw_data_dict, columns_to_keep):
        
        
    #     selected_data_dict = {}
    #     for market, raw_data_aux in raw_data_dict.items():
    #         raw_data_aux = raw_data_aux[columns_to_keep].copy()
    #         selected_data_dict[market] = raw_data_aux.set_index('datetime')
        
    #     return selected_data_dict
    
    @staticmethod
    def _clean_raw_database_data(raw_data_dict, columns_to_keep):
        selected_data_dict = {}
        for market, raw_data_aux in raw_data_dict.items():
            # Ensure only the desired columns are selected
            raw_data_aux = raw_data_aux[columns_to_keep].copy()

            # Convert columns to the desired data types
            if 'delivery_start' in raw_data_aux.columns:
                raw_data_aux['delivery_start'] = pd.to_datetime(raw_data_aux['delivery_start'], errors='coerce')
            if 'datetime' in raw_data_aux.columns:
                raw_data_aux['datetime'] = pd.to_datetime(raw_data_aux['datetime'], errors='coerce')
            if 'delivery_end' in raw_data_aux.columns:
                raw_data_aux['delivery_end'] = pd.to_datetime(raw_data_aux['delivery_end'], errors='coerce')
            if 'product_type' in raw_data_aux.columns:
                raw_data_aux['product_type'] = raw_data_aux['product_type'].astype(str)
            if 'delivery' in raw_data_aux.columns:
                raw_data_aux['delivery'] = raw_data_aux['delivery'].astype(str)
            
            # Convert remaining columns to float
            for col in raw_data_aux.columns:
                if col not in ['delivery_start', 'delivery_end', 'product_type', 'delivery', 'datetime']:
                    raw_data_aux[col] = pd.to_numeric(raw_data_aux[col].str.replace(',','.'), errors='coerce')
            
            # Set 'datetime' as the index if it exists
            if 'datetime' in raw_data_aux.columns:
                selected_data_dict[market] = raw_data_aux.set_index('datetime')
            else:
                selected_data_dict[market] = raw_data_aux
        
        return selected_data_dict
        
        
    @staticmethod
    def build_sql_queries_from_groupped_list(schema_name, data_2d_list):
        sql_queries = []
    
        # Extract the unique markets from the first sublist
        market_list_unique = data_2d_list[0]
    
        # Extract the corresponding lists
        delivery_start_lists = data_2d_list[1]
        delivery_type_lists = data_2d_list[2]
        product_type_lists = data_2d_list[3]
    
        # Loop through each unique market
        for i, market in enumerate(market_list_unique):
            table_name = f"{market}"
    
            # Get the corresponding lists for the current market
            delivery_start_list = delivery_start_lists[i]
            delivery_type_list = delivery_type_lists[i]
            product_type_list = product_type_lists[i]
    
            # Prepare the individual queries for each set of aligned elements
            individual_queries = []
            for dstart, dtype, ptype in zip(delivery_start_list, delivery_type_list, product_type_list):
                # Handle the 'eua' market differently by formatting delivery_start to query only December dates
                if market.lower() == 'eua' and isinstance(dstart, dt.datetime):
                    delivery_start_condition = f"delivery_start LIKE '{dstart.year}-12%'"
                else:
                    # Format delivery_start_list dates to 'YYYY-MM-DD'
                    if isinstance(dstart, dt.datetime):
                        dstart = dstart.strftime('%Y-%m-%d')
                    delivery_start_condition = f"delivery_start = '{dstart}'"
    
                # Capitalize the delivery type
                dtype_capitalized = dtype.capitalize()
    
                # Create the WHERE conditions for the aligned elements
                product_type_condition = f"product_type = '{ptype}'"
                delivery_type_condition = f"delivery = '{dtype_capitalized}'"
    
                # Combine conditions into a single WHERE clause
                where_clause = f"{product_type_condition} AND {delivery_start_condition} AND {delivery_type_condition}"
    
                # Append the individual query
                individual_queries.append(f"({where_clause})")
    
            # Combine all individual queries using OR
            combined_where_clause = " OR ".join(individual_queries)
    
            # Build the SQL query for the current market
            sql_query = f"""
            SELECT *
            FROM "{schema_name}"."{table_name}"
            WHERE {combined_where_clause};
            """
    
            sql_queries.append(sql_query.strip())
    
        return sql_queries
    
    @staticmethod
    def build_sql_queries_for_product_types(schema_name, data_2d_list):
        sql_queries = []

        # Extract the unique markets from the first sublist in data_2d_list
        market_list = data_2d_list[0]

        # Define the allowed product types
        allowed_product_types = ["Month", "Quarter", "Season", "Year", "Dec"]

        # Create the WHERE clause for the fixed product types
        product_type_conditions = " OR ".join([f"product_type = '{ptype}'" for ptype in allowed_product_types])

        # Calculate the target date (1st Jan, 4 years from today)
        target_date = dt.datetime(dt.datetime.now().year + 4, 1, 1).strftime('%Y-%m-%d')

        # Loop through each market and construct the query
        for market in market_list:
            table_name = f"{market}"

            # Build the SQL query for the current market
            sql_query = f"""
            SELECT *
            FROM "{schema_name}"."{table_name}"
            WHERE ({product_type_conditions})
            AND delivery_start < '{target_date}';
            """
            sql_queries.append(sql_query.strip())

        return sql_queries

    
    @staticmethod
    def generate_contracts(grouped_lists):
        # Extract components from grouped_lists
        markets = grouped_lists[0]
        delivery_start_lists = grouped_lists[1]
        delivery_type_lists = grouped_lists[2]
        product_type_lists = grouped_lists[3]
    
        contracts = []
    
        # Loop through each market and corresponding data
        for market_idx, market in enumerate(markets):
            delivery_starts = delivery_start_lists[market_idx]
            delivery_types = delivery_type_lists[market_idx]
            product_types = product_type_lists[market_idx]
    
            # Iterate over the corresponding delivery start, delivery type, and product type
            for dstart, dtype, ptype in zip(delivery_starts, delivery_types, product_types):
                # Convert delivery start to string if it's a pandas.Timestamp
                if isinstance(dstart, dt.datetime):
                    dstart_date = dstart
                elif isinstance(dstart, str):
                    dstart_date = dt.datetime.strptime(dstart, '%Y-%m-%d')
                else:
                    raise TypeError(f"Unsupported type for delivery start: {type(dstart)}")
    
                # Determine the contract name based on product type
                market_upper = market.upper()  # Ensure the full market name is in uppercase
    
                if ptype == "Month":
                    # Use month as the identifier (e.g., M_2_25 for February 2025)
                    contract = f"{market_upper}_{dtype[0].upper()}_M_{dstart_date.month}_{str(dstart_date.year)[-2:]}"
                elif ptype == "Quarter":
                    # Calculate the quarter and use it as the identifier (e.g., Q_2_25 for Q2 2025)
                    quarter = (dstart_date.month - 1) // 3 + 1
                    contract = f"{market_upper}_{dtype[0].upper()}_Q_{quarter}_{str(dstart_date.year)[-2:]}"
                elif ptype == "Year":
                    # Use 1 as the identifier for the year (e.g., Y_1_25 for the year 2025)
                    contract = f"{market_upper}_{dtype[0].upper()}_Y_1_{str(dstart_date.year)[-2:]}"
                elif ptype == "Season":
                    # Check if the season is Winter (W) or Summer (S)
                    if dstart_date.month == 10 and dstart_date.day == 1:
                        contract = f"{market_upper}_{dtype[0].upper()}_W_{str(dstart_date.year)[-2:]}"
                    elif dstart_date.month == 4 and dstart_date.day == 1:
                        contract = f"{market_upper}_{dtype[0].upper()}_S_{str(dstart_date.year)[-2:]}"
                    else:
                        continue  # Skip if the start date does not match a valid season
                elif ptype == "Dec":
                    # Check if the delivery start is the first of December
                    if dstart_date.month == 12 and dstart_date.day == 1:
                        contract = f"{market_upper}_{dtype[0].upper()}_DEC_12_{str(dstart_date.year)[-2:]}"
                    else:
                        continue  # Skip if the start date is not the first of December
                else:
                    continue  # Skip if product type doesn't match Month, Quarter, Year, Season, or Dec
    
                # Append the contract to the list
                contracts.append(contract)
    
        return contracts











        
        
        
if __name__== '__main__':
    params_dict = {}
    params_dict['product_list'] = ['M_2', 'Q_4', 'Y_1', 'W_0', 'WKND_1', 'D_3']*2
    params_dict['market_list'] = ['de'] * 5 + ['fr'] * 3 + ['hu']*2 + ['fr']*2
    params_dict['delivery_list'] = ['base']*3 + ['peak']*4 + ['base']*3 + ['peak']*2
    params_dict['eD'] = dt.datetime(2024,11,6)
    
    fdc = FuturesDataCollector(params_dict)
    
  
    final_data = fdc.get_data_from_database()
    

        
        
        
        
        
        