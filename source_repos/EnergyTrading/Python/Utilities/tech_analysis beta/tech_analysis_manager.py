import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

import pandas as pd
import numpy as np
import re
import datetime as dt
from copy import deepcopy

from Utilities.tech_analysis import ENUMS, data_loader
from Utilities.fund_analysis.fund_analysis.utils import spreads_creation
from Utilities.fund_analysis.fund_analysis import input_data


class DataError(Exception):
    pass

class MissingDataAfterMerge(DataError):
    pass

class TechAnalysis_manager:
    def __init__(self, markets: list=None, raw_data = None):
        self._markets = markets
        self._raw_data = None
        self._raw_ps_data = None
        self._raw_spot_data = {}
        
        
    @property
    def raw_data(self):
        if self._raw_data is None:
            self.load_data()
        return self._raw_data
    
    @property
    def raw_ps_data(self):
        if self._raw_ps_data is None:
            self.load_data()
        return self._raw_ps_data
    
    @property
    def raw_spot_data(self):
        if not self._raw_spot_data:
            self.load_spot_data()
        return self._raw_spot_data
    
    @property
    def markets(self):
        return self._markets
    
    def load_data(self):
        self._raw_data = data_loader.get_raw_prices(markets=self.markets)
    
    def _get_contract_params(self,contract):
        # Contract structure:
        #   "DE_B_M_2_25"
        market, del_type, product, period, year = contract.split('_')
        # del start/ del end
        delivery_start, delivery_end = spreads_creation.get_abs_product_period(product=contract)
        delivery_type = {'B': 'Base',
                    'P': 'Peak'}[del_type]
        return market, delivery_start, delivery_end, delivery_type
    
    def load_spot_data(self):
        params_dict = {
                'market_list' : self.markets,
                'product_list' : ['M_1'],
                'delivery_list' : ['base'],
                'year_list' : [None],
                'sD' : dt.datetime(2019,1,1),
                'eD' : dt.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0),
                'cont' : False
                }
        # Power
        power_inst = input_data.power.Power(params_dict)
        power_inst.get_da_data()
        gas_inst = input_data.gas.Gas(params_dict)
        gas_inst.get_da_data()
        eua_inst = input_data.eua.Eua(params_dict)
        eua_inst.get_da_data()

        self._raw_spot_data.update(power_inst.da_data)
        self._raw_spot_data['ttf'] = gas_inst.da_data['ttf']
        self._raw_spot_data['eua'] = eua_inst.da_data['eua']
    
    @staticmethod
    def _get_common_columns(dfs_list):
        """
        Extracts columns with expiry years from all DataFrames, ensuring all years 
        present in spread legs are included instead of filtering strictly by common years.
        """
        # Collect all unique years present in all DataFrames
        all_years = set()
        for df in dfs_list:
            years = {re.findall(r'\d{2}$', col)[0] for col in df.columns if re.findall(r'\d{2}$', col)}
            all_years.update(years)  # Collect all unique years
        
        # Now filter each DataFrame to keep only columns that match any of the identified years
        filtered_dfs = []
        for df in dfs_list:
            valid_cols = [col for col in df.columns if col[-2:] in all_years]
            filtered_dfs.append(df[valid_cols].copy())

        return filtered_dfs, sorted(all_years)  # Sorting ensures aligned processing

    
    @staticmethod
    def _compute_hours(product_type, year_abv, period, delivery_type):
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

    def _compute_weighted_sum(self, dfs_list, weights, spread_operator=None):
        """
        Computes a weighted sum while ensuring proper alignment of shifted contract legs.
        Optionally applies a custom spread operator.
        
        - Merges all contract legs based on their datetime index.
        - Ensures contracts are properly aligned before computing the spread.
        - Drops any rows with missing data (ensures all legs contribute to the spread).
        
        If spread_operator is provided:
        - If callable, it is applied to the merged DataFrame.
        - If a string expression, temporary column names (col0, col1, ...) are assigned
            (in the same order as the merged columns) and then the expression is evaluated.
        
        :param dfs_list: List of Pandas DataFrames for contract legs.
        :param weights: List of corresponding weights.
        :param spread_operator: Optional; if provided, used instead of the default weighted sum.
                                It can be either a callable or a string expression.
        :return: DataFrame containing the computed spread.
        """
        
        # Ensure number of weights matches number of DataFrames
        if len(weights) != len(dfs_list):
            raise ValueError("Number of weights must match number of DataFrames")
        
        # Create a spread name based on the first DataFrame's column name suffix.
        spread_name = f"spread_{dfs_list[0].columns[0].split('_')[-1]}"
        
        # Step 1: Merge all DataFrames on the datetime index using an inner join.
        combined_df = pd.concat(dfs_list, axis=1, join="inner")
        
        # Step 2: Drop any rows with missing data.
        valid_data_df = combined_df.dropna()
        if valid_data_df.empty:
            print("No valid data after merging contract legs for spread calculation.")
            return None
        
        # Step 3: Compute the spread.
        if spread_operator is None:
            # Default weighted sum using dot product.
            valid_data_df[spread_name] = np.dot(valid_data_df.values, np.array(weights).reshape(-1, 1))
        else:
            if callable(spread_operator):
                # Apply the custom function.
                valid_data_df[spread_name] = spread_operator(valid_data_df)
            elif isinstance(spread_operator, str):
                # Work on a copy to avoid altering the original columns.
                temp_df = valid_data_df.copy()
                # Assume that the relevant columns are in the same order as in dfs_list.
                # Rename only the first len(weights) columns to temporary names.
                n = len(weights)
                original_cols = temp_df.columns[:n]
                temp_names = {col: f"col{i}" for i, col in enumerate(original_cols)}
                temp_df = temp_df.rename(columns=temp_names)
                # Evaluate the provided string expression.
                # For example, spread_operator might be: "col0 / (col1 + 0.2*col2)"
                temp_df[spread_name] = temp_df.eval(spread_operator)
                valid_data_df[spread_name] = temp_df[spread_name]
            else:
                raise ValueError("spread_operator must be a callable or a string expression")
        
        return valid_data_df[[spread_name]]

    def _get_ps_for_gas(self, base_df, start_date, end_date):
        temp = self.raw_spot_data['ttf'].copy()
        temp = temp.resample('D').mean()
        temp = temp.loc[start_date:end_date].copy()
        contract = base_df.columns[0]
        # Get next month contract name
        next_start_date = start_date + pd.DateOffset(months=1)
        next_month = str(next_start_date.month)
        next_year = str(next_start_date.year)[-2:]
        next_contract = '_'.join(contract.split('_')[:3] + [next_month, next_year])
        next_month_df = self.get_leg(next_contract)
        next_month_df = next_month_df.loc[start_date:end_date].copy()
        temp = pd.concat([temp, next_month_df],axis=1).ffill()
        ps_temp = ((temp['ttf'].cumsum() + ((end_date - temp.index).days.values+1) * temp[next_contract])/
                   ((end_date-start_date).days+1))
        ps_temp.name = contract
        ps_df = pd.DataFrame(ps_temp)
        return ps_df
    

    def _compute_projected_settlement(self, contract_legs, do_it=False):
        if not do_it:
            return contract_legs
        
        projected_settlements = {}
        updated_contract_dict = {}
        
        out_df = deepcopy(contract_legs)
        
        for contract_name, base_df in contract_legs.items():
            base_df = pd.DataFrame(base_df).copy()
            # Fetch base contract data
            if base_df is None or base_df.empty:
                continue  # Skip if base contract data is missing
            
            # Parse contract details from its name
            parts = contract_name.split("_")
            market, delivery_type, product_type, period, year = (
                parts[0], parts[1], parts[2], int(parts[3]), int(parts[4]) + 2000
            )


            # Determine the contract's time axis
            if product_type == "Q":
                start_month = (period - 1) * 3 + 1
                end_month = start_month + 2
            elif product_type == "S":
                start_month = 4 if period == 1 else 10
                end_month = 9 if period == 1 else 3
            elif product_type == "Y":
                start_month = 1
                end_month = 12
            elif product_type == 'M':
                if market.lower() == 'ttf':
                    start_month = period
                    start_date = dt.datetime(year, start_month, 1)
                    end_date = (pd.Timestamp(year, start_month, 1) + pd.offsets.MonthEnd(0))
                    months_range = pd.date_range(start=start_date, end=end_date, freq='MS')
                    out_df = self._get_ps_for_gas(base_df, start_date, end_date)
                    return out_df
                else:
                    continue
            else:
                continue  # Unsupported product type
            
            start_date = dt.datetime(year, start_month, 1)
            end_date = (pd.Timestamp(year, end_month, 1) + pd.offsets.MonthEnd(0)).date()
            months_range = pd.date_range(start=start_date, end=end_date, freq='MS')

            
            mapping = {}
            for current_month in months_range:
                if current_month > dt.datetime.now():
                    continue
                
                quarter_start_month = ((current_month.month - 1) // 3) * 3 + 1
                quarter_end = pd.Timestamp(current_month.year, quarter_start_month, 1) + pd.offsets.QuarterEnd(0)
                
                for target_month in months_range:
                    if target_month < current_month:
                        month_contract = f"{market}_{delivery_type}_M_{target_month.month}_{target_month.year % 100}"
                        hours = self._compute_hours('M', target_month.year % 100, target_month.month, delivery_type)
                        month_df = self.get_leg(month_contract)
                        if month_df is not None and not month_df.empty:
                            month_df = month_df.reset_index().drop_duplicates(subset=[month_contract]).set_index('datetime')
                            month_df = month_df.groupby(month_df.index).first()
                            if not month_df.empty:
                                last_price = month_df[month_contract].iloc[[-1]]
                                mapping[month_contract] = (last_price, 'M', hours)
                    elif target_month <= quarter_end:
                        month_contract = f"{market}_{delivery_type}_M_{target_month.month}_{target_month.year % 100}"
                        hours = self._compute_hours('M', target_month.year % 100, target_month.month, delivery_type)
                        month_df = self.get_leg(month_contract)
                        if month_df is not None and not month_df.empty:
                            month_df = month_df.reset_index().drop_duplicates(subset=[month_contract]).set_index('datetime')
                            month_df = month_df.groupby(month_df.index).first()
                            mapping[month_contract] = (
                                month_df.loc[current_month:current_month + pd.offsets.MonthEnd(0), month_contract],
                                'M', hours)
                    else:
                        quarter = (target_month.month - 1) // 3 + 1
                        hours = self._compute_hours('Q', target_month.year % 100, quarter, delivery_type)
                        quarter_contract = f"{market}_{delivery_type}_Q_{quarter}_{target_month.year % 100}"
                        quarter_df = self.get_leg(quarter_contract)
                        if quarter_df is not None and not quarter_df.empty:
                            quarter_df = quarter_df.reset_index().drop_duplicates(subset=[quarter_contract]).set_index('datetime')
                            quarter_df = quarter_df.groupby(quarter_df.index).first()
                            mapping[quarter_contract] = (
                                quarter_df.loc[current_month:current_month + pd.offsets.MonthEnd(0), quarter_contract],
                                'Q', hours)
                
                for key, a in mapping.items():
                    assert a[0].index.is_unique, f"Index in mapping for key '{key}' is not unique."
                if mapping:
                    combined_data = pd.concat([a[0] for a in mapping.values()], axis=1, keys=list(mapping.keys())).ffill().dropna()
                else:
                    return out_df
                weights = [a[-1] for a in mapping.values()]
                contract_series = pd.Series((combined_data * weights).sum(axis=1) / sum(weights), name=contract_name)
                projected_settlement_column = pd.DataFrame(contract_series)
                
                completed_df = pd.concat([out_df, projected_settlement_column]).ffill()
                completed_df = completed_df.reset_index().drop_duplicates().set_index('datetime')
                out_df = completed_df.dropna().copy()
                
        return out_df

    # Get spot data/distributions for the spread
    def get_historical_spot(self, spread_legs: list, leg_weights: list = [1, -1], spread_operator=None):
        legs_data = []
        # Assemble leg data from each contract
        for contract in spread_legs:
            market, delivery_start, delivery_end, delivery_type = self._get_contract_params(contract)
            temp = self.raw_spot_data[market.lower()][[market.lower()]].sort_index().copy()
            temp = self._filter_spot_data(temp, market, delivery_start, delivery_end, deltype=delivery_type)
            legs_data.append(temp.resample('D').mean())

        # Combine legs data into one DataFrame and drop rows with missing values.
        spread_df = pd.concat(legs_data, axis=1).dropna()
        if len(spread_df) < 1:
            raise MissingDataAfterMerge("No valid prices after spread legs prices merge.")
        
        # If no spread_operator is provided, default to a dot product with leg_weights.
        if spread_operator is None:
            spread_df['spread_value'] = np.dot(spread_df[spread_legs].values,
                                            np.array(leg_weights).reshape(-1, 1))
        else:
            # If spread_operator is a callable function, use it directly.
            if callable(spread_operator):
                spread_df['spread_value'] = spread_operator(spread_df)
            # If spread_operator is a string, use pd.eval.
            elif isinstance(spread_operator, str):
                # Assign temporary column names to each leg column.
                for i, col in enumerate(spread_legs):
                    spread_df[f'col{i}'] = spread_df[col]
                # Evaluate the expression.
                spread_df['spread_value'] = spread_df.eval(spread_operator)
            else:
                raise ValueError("spread_operator must be a callable or a string expression")
        
        return spread_df[['spread_value']]
    
    # GHR operator
    @staticmethod
    def ghr_operator(df):
        col1, col2, col3 = df.columns
        return df[col1]/(df[col2] + df[col3]*0.2)
    
    # GHR spread operator
    @staticmethod
    def ghr_spread_operator(df):
        cols = df.columns
        return (df.iloc[:,0]/(df.iloc[:,1] + df.iloc[:,2]*0.2)) - (df.iloc[:,3]/(df.iloc[:,4] + df.iloc[:,5]*0.2))

    # GHR spread operator
    @staticmethod
    def ghr_spread__operator(df):
        cols = df.columns
        return (df.iloc[:,0]/(df.iloc[:,1] + df.iloc[:,2]*0.2)) - (df.iloc[:,3]/(df.iloc[:,4] + df.iloc[:,5]*0.2))

    # Helper for extracting base/peak hours
    @staticmethod
    def _filter_spot_data(df, market, delivery_start, delivery_end, deltype='base'):
        # Resample ttf and eua to hourly
        if market.lower() in ['ttf', 'eua']:
            df.iloc[-1] = np.nan
            df = df.resample('h').ffill().iloc[:-1].copy()
        # Filter rows based on month-day range (ignoring the year)
        start_md = delivery_start.strftime('%m-%d')
        end_md = delivery_end.strftime('%m-%d')
        
        if start_md <= end_md:
            mask = (df.index.strftime('%m-%d') >= start_md) & (df.index.strftime('%m-%d') <= end_md)
        else:
            # For date ranges that wrap around the year end (e.g. Dec 20 to Jan 10)
            mask = (df.index.strftime('%m-%d') >= start_md) | (df.index.strftime('%m-%d') <= end_md)
        
        df = df.loc[mask]
        
        # If deltype is "base", return the date-filtered DataFrame as-is.
        if deltype.lower() in ['base']:
            return df
        else:
            # For "peak", further filter by hour and weekday.
            df = df.copy()
            df['hour'] = df.index.hour
            df['weekday'] = df.index.weekday
            df = df.loc[(df['hour'] > 7) & (df['hour'] < 20) & (df['weekday'] < 4)].copy()
            return df.drop(['hour', 'weekday'], axis=1)
    
    # Fetch single contract (use for outright and spread as well)
    def get_leg(self, contract,
                columns_to_fetch:list = ['datetime', 'settlement_price']):
        
        market, delivery_start, delivery_end, delivery_type = self._get_contract_params(contract)
        out_df = self.raw_data[market.lower()].copy()
        out_df = out_df.sort_values('datetime')
        if contract.split('_')[0].lower() in ['eua']:
            out_df = out_df.loc[
                (   (out_df['delivery_start'].dt.month == 12) &  # Datetime belongs to December
                    (out_df['delivery_start'].dt.year == delivery_start.year)  # Ensure delivery_start year matches
                )
            ].copy()

        else:            
            out_df = out_df.loc[((out_df['delivery']==delivery_type)&
                                (out_df['delivery_start']==delivery_start.normalize())&
                                (out_df['delivery_end']==delivery_end.normalize()))].copy()
        out_df = out_df.loc[:,columns_to_fetch].copy()  
        out_df = out_df.set_index('datetime').copy()
        out_df = out_df.rename(columns={'settlement_price': contract})
        out_df = out_df[~out_df.index.duplicated(keep='last')]

        # Add projected settlement
        if contract.split('_')[0].lower() not in ['eua', 'ttf']:
            # Ensure out_df is a DataFrame before passing to _compute_projected_settlement
            if isinstance(out_df, pd.Series):
                out_df = out_df.to_frame()
            out_df = self._compute_projected_settlement({contract: out_df}) # Pass as dict
            if out_df is not None: # Check if computation was successful
                # Original contract variable should be a string.
                # If it has become a list like ['contract_name'], extract the string.
                contract_key = contract
                if isinstance(contract, list) and len(contract) == 1 and isinstance(contract[0], str):
                    contract_key = contract[0]

                # --- MODIFIED BLOCK START ---
                # current_out_df_val holds the direct output of _compute_projected_settlement
                current_out_df_val = out_df 
                processed_successfully = False

                if isinstance(current_out_df_val, dict):
                    if contract_key in current_out_df_val:
                        df_candidate = current_out_df_val[contract_key]
                        if isinstance(df_candidate, pd.DataFrame) and contract_key in df_candidate.columns:
                            out_df = df_candidate[[contract_key]] # Assign to the main out_df
                            processed_successfully = True
                        else:
                            print(f"Warning (get_leg): Value for '{contract_key}' in projected dict is not a valid DataFrame or missing column.")
                    else:
                        print(f"Warning (get_leg): Key '{contract_key}' not found in projected dictionary.")
                elif isinstance(current_out_df_val, pd.DataFrame):
                    if contract_key in current_out_df_val.columns:
                        out_df = current_out_df_val[[contract_key]] # Assign to the main out_df
                        processed_successfully = True
                    else:
                        print(f"Warning (get_leg): Column '{contract_key}' not found in projected DataFrame.")
                # If current_out_df_val was None, the outer 'if out_df is not None:' already handled it.
                # This else covers other unexpected types if any.
                elif current_out_df_val is not None: # Explicitly check not None here, as outer if already did.
                    print(f"Warning (get_leg): Projected settlement returned unexpected type: {type(current_out_df_val)} for {contract_key}.")
                
                if not processed_successfully:
                    # If not processed successfully, out_df still holds current_out_df_val (the problematic output).
                    # The comprehensive fallback logic below will attempt to deal with this.
                    print(f"Info (get_leg): Projection for {contract_key} was not successful. Fallback will be attempted on current state of out_df: {type(out_df)}.")
                # --- MODIFIED BLOCK END ---
            # else: out_df was None from _compute_projected_settlement, comprehensive fallback below will handle.
            
            # The following 'if' block is the comprehensive fallback logic.
            # It checks the state of out_df. If projection was successful, out_df is a valid single-column DataFrame.
            # If projection failed, out_df might be the problematic dict/DataFrame/None,
            # and this check should fail, triggering the re-fetch of original data.
            if not (isinstance(out_df, pd.DataFrame) and contract_key in out_df.columns and len(out_df.columns) == 1):
                # This 'if' condition effectively replaces the original 'else' for the block:
                # "if out_df is not None and contract in out_df:"
                # It means either out_df is None, or it's not a DataFrame, or the contract_key column is missing,
                # or it has more than one column.
                print(f"Projected settlement failed or yielded unexpected format for {contract_key}. Re-fetching original data.")
                # Re-fetch original if necessary or handle as error
                # For now, just ensure it's a DataFrame
                if isinstance(out_df, pd.Series):
                    out_df = out_df.to_frame()
                elif out_df is None: # If _compute_projected_settlement returned None
                    # Re-fetch original data for this leg if it was overwritten or became None
                    # This is a simplified fallback; ideally, log this or handle more robustly
                    temp_out_df = self.raw_data[market.lower()].copy()
                    temp_out_df = temp_out_df.sort_values('datetime')
                    if contract.split('_')[0].lower() in ['eua']:
                        temp_out_df = temp_out_df.loc[
                            (   (temp_out_df['delivery_start'].dt.month == 12) &
                                (temp_out_df['delivery_start'].dt.year == delivery_start.year)
                            )
                        ].copy()
                    else:            
                        temp_out_df = temp_out_df.loc[((temp_out_df['delivery']==delivery_type)&
                                            (temp_out_df['delivery_start']==delivery_start.normalize())&
                                            (temp_out_df['delivery_end']==delivery_end.normalize()))].copy()
                    temp_out_df = temp_out_df.loc[:,columns_to_fetch].copy()  
                    temp_out_df = temp_out_df.set_index('datetime').copy()
                    temp_out_df = temp_out_df.rename(columns={'settlement_price': contract})
                    out_df = temp_out_df[~temp_out_df.index.duplicated(keep='last')]


        return out_df

    def get_instrument_data(self, contract_object: str) -> pd.Series:
        """
        Fetches price data for a single instrument and returns it as a pandas Series.
        contract_object: The contract identifier string (e.g., "DE_B_M_2_25").
        """
        # Assuming get_leg returns a DataFrame with the contract name as the column
        df_instrument = self.get_leg(contract=contract_object)
        if df_instrument is not None and not df_instrument.empty:
            # Ensure the column name matches the contract_object for direct selection
            if contract_object in df_instrument.columns:
                return df_instrument[contract_object]
            else:
                # Fallback if the column name is different (e.g. 'settlement_price')
                # This case should ideally not happen if get_leg consistently names columns
                if len(df_instrument.columns) == 1:
                    return df_instrument.iloc[:, 0]
                else:
                    # Handle error: multiple columns or no matching column
                    raise ValueError(f"Could not find a unique price column for {contract_object} in DataFrame from get_leg.")
        else:
            # Handle error: no data returned for the instrument
            raise ValueError(f"No data found for instrument {contract_object}")

    def generate_historical_variants(self, current_spread_series: pd.Series, seasonality: bool = False) -> pd.DataFrame:
        """
        Generates historical variants (Y-1, Y-2, Avg, Seasonality_Avg) for a given spread series.
        current_spread_series: A pandas Series representing the calculated spread (e.g., from a formula).
                               The Series should have a DatetimeIndex.
        seasonality: A boolean flag indicating whether to calculate seasonality-adjusted average.
        """
        if not isinstance(current_spread_series.index, pd.DatetimeIndex):
            raise ValueError("current_spread_series must have a DatetimeIndex.")

        historical_df = pd.DataFrame(index=current_spread_series.index)
        
        # Y-1
        historical_df['Y-1'] = current_spread_series.shift(freq=pd.DateOffset(years=1))
        
        # Y-2
        historical_df['Y-2'] = current_spread_series.shift(freq=pd.DateOffset(years=2))
        
        # Y-3
        historical_df['Y-3'] = current_spread_series.shift(freq=pd.DateOffset(years=3))

        # Y-4
        historical_df['Y-4'] = current_spread_series.shift(freq=pd.DateOffset(years=4))
        
        # Y-5
        historical_df['Y-5'] = current_spread_series.shift(freq=pd.DateOffset(years=5))


        # Average of Y-1 to Y-5
        # We need to align the dates for averaging. The easiest way is to shift them all to the current year's day-of-year.
        shifted_years = []
        current_year_index = current_spread_series.index.map(lambda dt: dt.replace(year=current_spread_series.index.year.max()))

        for i in range(1, 6): # Y-1 to Y-5
            shifted_series = current_spread_series.copy()
            # Shift data back by i years
            shifted_series.index = shifted_series.index - pd.DateOffset(years=i)
            # Align to current year's day-of-year for averaging
            # This creates a common index based on month and day for averaging across years.
            temp_idx = shifted_series.index.map(lambda dt: dt.replace(year=current_spread_series.index.year.max()))
            shifted_series.index = temp_idx
            shifted_years.append(shifted_series.rename(f"Y-{i}_aligned"))

        avg_df = pd.concat(shifted_years, axis=1)
        historical_df['Avg'] = avg_df.mean(axis=1)
        historical_df.index = current_year_index # Ensure final index is aligned with original series for plotting

        if seasonality:
            # For seasonality, we typically normalize or use z-scores.
            # Here, we'll calculate a simple seasonality-adjusted average.
            # This example calculates z-scores for each year and then averages them.
            # This is a placeholder for potentially more complex seasonality logic.
            
            # Calculate z-scores for each shifted year
            z_scores_list = []
            for col in avg_df.columns: # Iterate through Y-1_aligned, Y-2_aligned etc.
                series = avg_df[col].dropna()
                if not series.empty and series.std() != 0:
                    z_score = (series - series.mean()) / series.std()
                    z_scores_list.append(z_score)
            
            if z_scores_list:
                seasonality_avg_z = pd.concat(z_scores_list, axis=1).mean(axis=1)
                # To convert back to original scale (approximately), we can scale by overall std and add overall mean
                # This is a simplification. True seasonal adjustment might involve more sophisticated models.
                overall_mean = current_spread_series.mean()
                overall_std = current_spread_series.std()
                if overall_std != 0:
                     historical_df['Seasonality_Avg'] = (seasonality_avg_z * overall_std) + overall_mean
                else: # Handle case with no variance
                    historical_df['Seasonality_Avg'] = overall_mean
            else:
                historical_df['Seasonality_Avg'] = np.nan


        # Ensure the historical_df has the same index as the input series for direct plotting
        # Reindex and fill forward to handle cases where historical data might not align perfectly
        # This ensures that the plot_chart function receives a DataFrame that aligns with its expectations.
        final_historical_df = pd.DataFrame(index=current_spread_series.index)
        for col in ['Y-1', 'Y-2', 'Y-3', 'Y-4', 'Y-5', 'Avg', 'Seasonality_Avg']:
            if col in historical_df:
                # Create a temporary series with the original index, then map values from historical_df
                temp_series = pd.Series(index=current_spread_series.index, dtype=float)
                
                # Map values from historical_df (which might have a day-of-year based index for Avg/Seasonality_Avg)
                # to the original series's datetime index.
                if col in ['Avg', 'Seasonality_Avg']: # These were calculated on a common M-D index
                    # Map based on month and day
                    map_idx = temp_series.index.map(lambda dt: dt.replace(year=historical_df.index.year.max()))
                    temp_series = historical_df[col].reindex(map_idx).set_axis(temp_series.index)

                else: # For Y-1, Y-2 etc, they are already shifted versions of original index
                    temp_series = historical_df[col]

                final_historical_df[col] = temp_series.reindex(current_spread_series.index).ffill().bfill()


        return final_historical_df.dropna(how='all', axis=1)


    def get_spread(self, spread_legs: list,
               leg_weights: list = [1, -1],
               columns_to_fetch: list = ['datetime', 'settlement_price'],
               spread_operator=None):
        """
        Get the spread from the legs data. This function fetches data for each leg,
        concatenates them, and then computes the spread value. By default, the spread
        is computed as a weighted sum (dot product) of the leg values with leg_weights.
        
        Alternatively, a custom spread operator can be provided:
        - If spread_operator is a callable, it will be called with the spread DataFrame
            and must return a Series of spread values.
        - If spread_operator is a string, it is assumed to be an expression that uses
            temporary column names (col0, col1, ...) to compute the spread (via pd.eval).
        
        Parameters:
        spread_legs: list of leg identifiers (also used as column names in the spread DataFrame).
        leg_weights: list of weights (default computes first leg minus second).
        columns_to_fetch: list of columns to fetch for each leg.
        spread_operator: Optional custom operator (callable or string expression) for spread calculation.
        
        Returns:
        DataFrame with a single column 'spread_value' containing the computed spread.
        """
        legs_list = []
        for contract in spread_legs:
            legs_list.append(self.get_leg(contract=contract,
                                        columns_to_fetch=columns_to_fetch))
        spread_df = pd.concat(legs_list, axis=1).dropna()
        if len(spread_df) < 1:
            raise MissingDataAfterMerge("No valid prices after spread legs prices merge.")
        
        # If no spread operator is provided, default to weighted dot product.
        if spread_operator is None:
            spread_df['spread_value'] = np.dot(spread_df[spread_legs].values,
                                            np.array(leg_weights).reshape(-1, 1))
        else:
            # If a callable operator is provided, use it.
            if callable(spread_operator):
                spread_df['spread_value'] = spread_operator(spread_df)
            # If an expression string is provided, use temporary column names.
            elif isinstance(spread_operator, str):
                for i, col in enumerate(spread_legs):
                    spread_df[f'col{i}'] = spread_df[col]
                spread_df['spread_value'] = spread_df.eval(spread_operator)
            else:
                raise ValueError("spread_operator must be a callable or a string expression")
        return spread_df[['spread_value']]

        
    # Fetch single contract (use for outright and spread as well)
    def get_history_legs(self, contract,
                columns_to_fetch:list = ['datetime', 'settlement_price']):  
        
        market, delivery_start, delivery_end, delivery_type = self._get_contract_params(contract)
        out_df = self.raw_data[market.lower()].copy()
        if contract.split('_')[0].lower() in ['eua']:
            out_df = out_df.loc[
                (   (out_df['delivery_start'].dt.month == 12)   # Ensure delivery_start year matches
                )
            ].copy()
        else:
            out_df = out_df.loc[
                        (out_df['delivery'] == delivery_type) &
                        (out_df['delivery_start'].dt.strftime('%m-%d') == delivery_start.strftime('%m-%d')) &
                        (out_df['delivery_end'].dt.strftime('%m-%d') == delivery_end.strftime('%m-%d'))
                    ].copy()
        if 'delivery_start' not in columns_to_fetch:
            columns_to_fetch = columns_to_fetch + ['delivery_start']
        out_df = out_df.loc[:,columns_to_fetch].copy()
        out_df = out_df.set_index('datetime').copy()
        out_df = out_df.rename(columns={'settlement_price': contract})
        
        # Sample DataFrame (Ensure datetime index)
        out_df['year'] = out_df['delivery_start'].dt.year  # Extract year from delivery_start
        # current_year = pd.Timestamp.now().year  # Get current year

        # Calculate past year differences (only if year < current_year)
        # out_df['year_diff'] = current_year - out_df['year']
        
        # # Delete when database will be updated for duplicities
        # out_df = out_df.drop_duplicates([contract])
        # out_df = out_df[~out_df.index.duplicated(keep='last')]


        # Store shifted series
        shifted_series_list = []

        contract_year = int(contract.split('_')[-1]) + 2000

        # Group by year of delivery_start
        for year, group in out_df.groupby('year'):
            year_diff = contract_year - year  # Compute shift amount

            # Shift index by the past year difference
            shifted_group = group.copy()
            new_col_name = f"{contract[:-2]}{str(year)[-2:]}"
            shifted_group = shifted_group.rename(columns={contract: new_col_name})[[new_col_name]].copy()
            shifted_group = self._compute_projected_settlement(shifted_group)
            shifted_group.index = shifted_group.index + pd.DateOffset(years=year_diff)

            # Modify contract variable (use it as column name with updated year)
            

            
            
            
            # Store only relevant shifted column with new index
            shifted_series_list.append(shifted_group)

        # Concatenate all shifted series along axis=1
        shifted_series_list = [df[~df.index.duplicated(keep='first')] for df in shifted_series_list]
        final_df =pd.concat(shifted_series_list, axis=1)
        # final_df = round(final_df.interpolate(method='linear', limit=5, limit_area='inside'),2)
        
        return final_df
    
    def get_history_spread(self, spread_legs: list, leg_weights: list = [1, -1],
                           columns_to_fetch: list = ['datetime', 'settlement_price'],
                           spread_operator=None,
                           seasonality=False):
        """
        Optimized historical spread calculation with dynamic shifting.

        - Calls `get_history_legs` once for all contracts.
        - Extracts available years from the first contract.
        - Dynamically shifts other contracts based on the difference in year_abv.
        - Passes fully aligned groups to `_compute_weighted_sum`.

        Returns:
            DataFrame with computed spread values.
        """

        # Fetch all history legs at once
        history_legs = {contract: self.get_history_legs(contract, columns_to_fetch) for contract in spread_legs}

        # Take the first contract's DataFrame and extract available years
        first_leg_df = history_legs[spread_legs[0]]
        available_years = sorted(set(int(re.findall(r'\d{2}$', col)[0]) for col in first_leg_df.columns if re.findall(r'\d{2}$', col)))

        # Prepare shifted spread leg groups
        spread_groups = []
        
        for target_year_abv in available_years:
            shifted_leg_group = []

            # Determine the year shift needed
            first_contract_year_abv = int(re.findall(r'\d{2}$', spread_legs[0])[0])
            shift_difference = target_year_abv - first_contract_year_abv

            for contract in spread_legs:
                contract_prefix = "_".join(contract.split("_")[:-1])
                contract_year_abv = int(re.findall(r'\d{2}$', contract)[0])  # Extract original contract's year

                # Shift the contract's year based on the difference
                shifted_contract_year = contract_year_abv + shift_difference
                shifted_contract = f"{contract_prefix}_{shifted_contract_year:02d}"

                # Check if the shifted contract exists in the dataset
                if shifted_contract in history_legs[contract].columns:
                    shifted_leg_group.append(history_legs[contract][[shifted_contract]])
                else:
                    break  # If any contract is missing, skip this group

            # Only include fully formed groups
            if len(shifted_leg_group) == len(spread_legs):
                spread_groups.append(shifted_leg_group)

        # Compute weighted spreads for each valid group
        spread_results = [self._compute_weighted_sum(dfs_list=group, weights=leg_weights, spread_operator=spread_operator) for group in spread_groups]

        # Combine results and return final spread DataFrame
        if spread_results:
            final_spread_df = pd.concat(spread_results, axis=1).dropna(how='all')
            final_spread_df = round(final_spread_df.interpolate(method='linear', limit=5, limit_area='inside'),2)
            if seasonality:
                # return round((final_spread_df - final_spread_df.min())/(final_spread_df.max()-final_spread_df.min())*100,1)
                z_score = round((final_spread_df - final_spread_df.mean())/
                             (final_spread_df.std()),2)
                return round((z_score - z_score.min())/(z_score.max()-z_score.min())*100,1)
            else:
                return final_spread_df
        else:
            raise MissingDataAfterMerge("No valid historical spread data found.")

    # Helper funciton for getting front contracts
    @staticmethod
    def get_front_contract(last_settle):
        next_month = str((last_settle + pd.DateOffset(months=1)).month)
        next_month_year = str((last_settle + pd.DateOffset(months=1)).year)[-2:]
        next_year = str(last_settle.year + 1)[-2:]
        if last_settle < dt.datetime(last_settle.year,12,1):
            this_dec_year = str(last_settle.year)[-2:]
        else:
            this_dec_year = str(last_settle.year + 1)[-2:]
        contracts = [f"TTF_B_M_{next_month}_{next_month_year}",
                     f"TTF_B_Y_1_{next_year}",
                     f"DE_B_M_{next_month}_{next_month_year}",
                     f"DE_B_Y_1_{next_year}",
                     f"EUA_B_Y_1_{this_dec_year}"]
        return contracts


    def get_rel_strenght(self, spread_legs: list,
               leg_weights: list = [1, -1],
               columns_to_fetch: list = ['datetime', 'settlement_price'],
               spread_operator=None):
        spread = self.get_spread(spread_legs=spread_legs,
                                 leg_weights=leg_weights,
                                 columns_to_fetch=columns_to_fetch,
                                 spread_operator=spread_operator)
        contracts = self.get_front_contract(spread.index[-1])
        contract_legs = []
        for contract in contracts:
            contract_legs.append(self.get_leg(contract))
        front_df = pd.concat(contract_legs,axis=1).dropna()
        front_df = pd.concat([front_df, spread],axis=1).dropna()
        rel_strenght_df = round((front_df - front_df.min())/(front_df.max()-front_df.min())*100,1)
        rel_strenght_df.columns = ['fm_gas', 'fy_gas', 'fm_de', 'fy_de', 'fdec_eua', 'spread']
        return rel_strenght_df.iloc[-63:]
    


    
if __name__=='__main__':


    markets = ['de', 'ttf', 'it', 'eua', 'sk', 'hu']
    inst = TechAnalysis_manager(markets=markets)
    spread_legs = ['DE_B_Q_4_25', 'FR_B_Q_4_25',
                   'DE_B_Q_1_26', 'FR_B_Q_1_26']
    leg_weights = [1, -1, -1, 1]
    spread_legs = ['IT_B_M_4_25', 'TTF_B_M_4_25', 'EUA_B_Y_1_25']
    leg_weights = [1,-2,-0.4]
    # spread_legs = ['CZ_P_Y_1_27', 'TTF_B_Y_1_27', 'EUA_B_Y_1_27', 'CZ_B_Y_1_27', 'TTF_B_Y_1_27', 'EUA_B_Y_1_27']
    # leg_weights = [1, -2, -0.4]
    columns_to_fetch = ['datetime', 'settlement_price']
    # inst.get_historical_spot(spread_legs=spread_legs,
    #                          spread_operator=inst.ghr_spread_operator)
    # leg_test = inst.get_history_spread(spread_legs=spread_legs,
    #                                    leg_weights=leg_weights,
    #                                     columns_to_fetch=columns_to_fetch)
    # spread_test = inst.get_spread(spread_legs=spread_legs,
    #                             leg_weights=leg_weights)

    # rel_strenght = inst.get_rel_strenght(spread_legs=spread_legs,
    #                       leg_weights=leg_weights)
    # spread_legs = ['DE_B_Q_1_26']
    # rel_strenght = inst.get_rel_strenght(spread_legs=spread_legs,
    #                       leg_weights=[1])

    # def ghr_operator(df):
    #     return ()

    legs = ['SK_B_Y_1_26', 'DE_B_Y_1_26', 'TTF_B_Y_1_26',
            'TTF_B_Q_1_26', 'TTF_B_Q_2_26', 'TTF_B_Q_3_26',
            'TTF_B_Q_4_26',
            'DE_B_Q_1_26', 'DE_B_Q_2_26', 'DE_B_Q_3_26',
            'DE_B_Q_4_26', 'EUA_B_Y_1_26']
    
    legs = ['DE_B_M_6_25', 'DE_B_M_7_25', 'DE_B_M_8_25', 'DE_B_M_9_25',
            'DE_B_M_10_25','DE_B_M_11_25', 'DE_B_Q_3_25','DE_B_Q_4_25']
    
    legs = ['SK_B_Q_3_25', 'SK_B_Q_4_25', 'SK_B_Q_1_26', 'SK_B_Y_1_26',
            'HU_B_Q_3_25', 'HU_B_Q_4_25', 'HU_B_Q_1_26', 'HU_B_Q_4_26', 'HU_B_Y_1_26']

    
    data_list = []

    for leg in legs:
        data_list.append(inst.get_leg(contract=leg))

    data = pd.concat(data_list,axis=1).dropna()
    data.to_excel(r'C:\Users\krajcovic\Documents\EIF\EnergoChem\data_power_de.xlsx')
    
    print('debug_stop')