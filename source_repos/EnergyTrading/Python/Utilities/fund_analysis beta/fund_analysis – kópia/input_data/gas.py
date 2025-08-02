"""
    Prices of fuels, power and euas
    
    Need to handle both fut curves and day ahead data
        for train and analysis
        
    Common methods will be:
        creating futures curve
        creating spot day ahead data
"""


import pandas as pd
import openpyxl
import numpy as np
import datetime as dt
import os
from copy import deepcopy
from fund_analysis.utils import ENUMS as enums
from .input_data import InputData as input_data
from Utilities.date_functions import start_date, end_date

class Gas(input_data):
    
    
    def __init__(self, params_dict, gas_markets=[]):
        super().__init__(params_dict=params_dict)
        self._gas_markets = gas_markets
        if len(self._gas_markets)<1:
            self.get_unique_markets()
        self.fut_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        self.da_data_history = {}
        
    @property
    def gas_markets(self):
        return self._gas_markets
        
    def get_unique_markets(self):
        self._gas_markets = list(np.unique([enums.get_gas_fut_mapping(a)
                            for a in self.unique_markets]))
        
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
        self.data_curve = {}
        
    def reset_data(self):
        self.fut_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        self.da_data_history = {}
        
    def get_fut_matrix(self):        
        for market in self.gas_markets:
            if not market in self.fut_matrix:
                schema_name = 'futures'
                table_name = enums.get_name_to_ice(market)
                temp_matrix = self.data_loader.get_data_db(schema_name=schema_name,
                                                            table_name=table_name,
                                                            datetime_col='datetime')
                temp_matrix.set_index('datetime',inplace=True)
                settle_columns = [a for a in temp_matrix.columns if 'SETTLE' in a]
                temp_matrix = temp_matrix[settle_columns].copy()
                temp_matrix.columns = [a.replace('_SETTLE', '')
                                        for a in temp_matrix.columns]
                self.fut_matrix[market] = temp_matrix
    
    def update_live_prices_from_file(self, market_df=None):
        today_date = pd.to_datetime(dt.date.today())
        file_path = '//192.168.10.91/data/LiveScreen_v01.xlsx'  # Replace with the path to your file
        last_modified_time = os.path.getmtime(file_path)
        modification_time = pd.to_datetime(dt.date.fromtimestamp(last_modified_time))
        if self.pivot_date == today_date:
            if modification_time != today_date:
                raise Exception('File not updated')
            else:
                gas_act = pd.read_excel(file_path, sheet_name='gas_main')
                gas_act.columns = ['product', 'tenor', 'bid', 'offer']
                gas_act = gas_act.iloc[1:].copy()
                gas_act['product'] = gas_act['product'].ffill()
                gas_act['mid'] = gas_act[['bid', 'offer']].mean(axis=1)
                gas_act = gas_act.loc[gas_act['product']!='Seasons'].copy()
                gas_act_exp = self.expand_live_prices_df(gas_act)
                gas_act_exp = self.add_adjusted_row(gas_act_exp, market_df, modification_time)
                gas_act_exp = gas_act_exp.interpolate()
            return gas_act_exp
        else:
            return market_df
                    
    @staticmethod
    def expand_live_prices_df(df):
        # List to hold the new rows
        expanded_rows = []

        # Iterate over each row in the DataFrame
        for idx, row in df.iterrows():
            product = row['product']
            tenor = int(row['tenor'])
            bid = row['bid']
            offer = row['offer']
            mid = row['mid']
            
            if product == 'Quarters':
                # Map quarters to months
                start_month = (tenor - 1) * 3 + 3  # Starting from Month 3
                months = [((start_month + i - 1) % 12) + 1 for i in range(3)]
                
                for month in months:
                    new_row = row.copy()
                    new_row['expanded_month'] = month
                    expanded_rows.append(new_row)
            elif product == 'Years':
                # Map years to months
                start_month = (tenor - 1) * 12 + 1
                months = [((start_month + i - 1) % 12) + 1 for i in range(12)]
                
                for month in months:
                    new_row = row.copy()
                    new_row['expanded_month'] = month
                    expanded_rows.append(new_row)
            else:
                # For other products, set expanded_month appropriately
                new_row = row.copy()
                if product == 'Months':
                    new_row['expanded_month'] = tenor
                else:
                    new_row['expanded_month'] = np.nan  # Set to NaN for products without a specific month
                expanded_rows.append(new_row)
        # Create a new DataFrame from the expanded rows
        expanded_df = pd.DataFrame(expanded_rows)

        # Convert 'tenor' and 'expanded_month' to integer where appropriate
        expanded_df['tenor'] = expanded_df['tenor'].astype(int)
        expanded_df['expanded_month'] = expanded_df['expanded_month'].astype('Int64')  # Allows NaN values

        # Sort the DataFrame by original 'product' and 'tenor'
        expanded_df.sort_values(by=['product', 'tenor'], inplace=True)
        expanded_df.reset_index(drop=True, inplace=True)
        expanded_df = expanded_df.loc[expanded_df['product'].isin(['Months', 'Quarters', 'Years'])].copy()
        return expanded_df
    
    @staticmethod
    def add_adjusted_row(expanded_df, df2, new_date):
        def get_months_for_product(product, tenor):
            if product == 'Months':
                return [int(tenor)]
            elif product == 'Quarters':
                start_month = (int(tenor) - 1) * 3 + 3  # Quarters start from month 3
                return [((start_month + i - 1) % 12) + 1 for i in range(3)]
            elif product == 'Years':
                start_month = (int(tenor) - 1) * 12 + 1
                return [((start_month + i - 1) % 12) + 1 for i in range(12)]
            else:
                return []
        # Sample DataFrame with monthly columns (M_1 to M_60)
        adjusted_df = df2.copy()

        # Initialize the new row with NaNs (will be updated)
        new_row = pd.Series(index=adjusted_df.columns, name=new_date, dtype=float)

        # Step 1: Place Month Values from expanded_df to new_row
        for idx, row in expanded_df.iterrows():
            product = row['product']
            tenor = row['tenor']
            expanded_month = row['expanded_month']
            mid = row['mid']
            
            # Skip rows where price is NaN
            if np.isnan(mid):
                continue
            
            # If the product is 'Months', directly place the price in the corresponding month column in new_row
            if product == 'Months' and expanded_month <= 60:
                column_name = f"M_{int(expanded_month)}"
                new_row[column_name] = mid

        # Step 2: Overlay Prices from Quarters and Years with Historical Patterns
        for idx, row in expanded_df.iterrows():
            product = row['product']
            tenor = row['tenor']
            mid = row['mid']
            
            # Skip rows where price is NaN or the product is 'Months'
            if product == 'Months' or np.isnan(mid):
                continue
            
            # Get the months covered by the current product (Quarters or Years)
            months = get_months_for_product(product, tenor)
            
            # Make sure the months are within the range [1, 60]
            months = [m for m in months if m <= 60]
            
            # Extract historical pattern for the corresponding months
            historical_values = adjusted_df.loc[:, [f"M_{m}" for m in months]].dropna().mean(axis=0)
            
            # If no historical values exist, skip this product
            if historical_values.empty:
                continue
            
            base_prices_period = historical_values.values
            
            # Calculate the shape by normalizing the historical values
            shape = base_prices_period / np.mean(base_prices_period) if np.mean(base_prices_period) != 0 else np.ones_like(base_prices_period)
            
            # Rescale the shape to match the period's price
            adjusted_prices_period = shape * mid
            
            # Overlay the adjusted prices into the new_row
            for i, month in enumerate(months):
                column_name = f"M_{month}"
                if pd.isna(new_row[column_name]):
                    new_row[column_name] = adjusted_prices_period[i]

        # Step 3: Fill any remaining NaN values in the new_row
        # We will use the historical average for each column to fill in the missing values
        for column in new_row.index:
            if pd.isna(new_row[column]):
                column_mean = adjusted_df[column].mean()
                new_row[column] = column_mean if not np.isnan(column_mean) else 0  # Fill with 0 if no historical data exists

        # Step 4: Append the new_row to adjusted_df using pd.concat()
        adjusted_df = pd.concat([adjusted_df, pd.DataFrame([new_row])])

        return adjusted_df

    # Example usage
    # adjusted_df = add_adjusted_row(expanded_df, df2, '2024-12-01')
    # print(adjusted_df.tail())
    
    def check_pivot_date(self, market_df):
        # Ensure pivot_date is in the index
        # assert self.pivot_date in market_df.index, f"pivot_date {self.pivot_date} is not in the market_df index"

        # Continue with the rest of the method
        print("Pivot date is present in the DataFrame index.")
        
    def get_curve(self):
        self.get_fut_matrix()
        for market, market_df in self.fut_matrix.items():
            market_df = self.update_live_prices_from_file(market_df=market_df.sort_index())
            if not market in self.data_curve:
                # Step 1: Create the initial `curve` for the market starting from `self.pivot_date`.
                # self.check_pivot_date(market_df)
                curve = market_df.loc[self.pivot_date, :].copy()
                # Remove '_base' from the index names
                curve.index = [a.replace('_base', '') for a in curve.index]
                # Create a list of start dates for the curve index (replace your logic accordingly)
                dates_list = [start_date(self.pivot_date, product)
                            if product.lower() not in ['wk', 'wknd'] else
                            start_date(self.pivot_date, 'w') if product.lower() in ['wk'] else None
                            for product in curve.index]
                # Set the curve index to these calculated dates
                curve.index = dates_list
                # Step 2: Get the DA (day-ahead) value
                if not market in self.da_data:
                    self.get_da_data()
                    
                # Assuming da is just a single value
                da_value = self.da_data[market].loc[self.pivot_date]
                # Step 3: Calculate the number of days between the pivot_date and the first date of the curve
                first_curve_date = curve.index[0]
                days_to_interpolate = (first_curve_date - self.pivot_date).days + 15  # Add 15 extra days for interpolation
                # Create a date range for this interpolation (from pivot_date to first_curve_date + 15 days)
                interpolation_dates = pd.date_range(start=self.pivot_date, periods=days_to_interpolate, freq='D')
                # Create a series for interpolation with da_value at the start and the first curve value at the end
                interpolation_series = pd.Series([da_value.iloc[0], curve.iloc[0]], index=[interpolation_dates[0], interpolation_dates[-1]])
                # Step 4: Interpolate between the da_value and the first value of the curve
                interpolated_values = interpolation_series.reindex(interpolation_dates).interpolate()
                # Step 5: Create an hourly version of the interpolated data
                interpolated_values = interpolated_values.resample('h').ffill()
                # Step 6: Combine the interpolated values with the curve
                # Now extend the original curve with the interpolated data (for days before the first date)
                curve = curve.combine_first(interpolated_values)
                curve.name = market
                curve.index.name = 'datetime'
                # Step 7: Resample the full curve to hourly data, filling forward
                curve = curve.resample('h').ffill()
                
                if not hasattr(self, 'curve_end_date'):
                    self.get_curve_start_end_date()
                curve = curve.loc[:self.curve_end_date].copy()
                self.data_curve[market] = pd.DataFrame(curve)
                
                    
    def get_da_data(self):
        for market in self.gas_markets:
            if not market in self.da_data_history:
                spot_table = market
                self.da_data_history[market] = self.data_loader.get_data_db(schema_name='spot',
                                                        table_name=spot_table,
                                                        datetime_col='datetime')
            da_temp = self.da_data_history[market].copy()
            da_temp.set_index('datetime',inplace=True)
            da_temp.rename(columns={'price': market}, inplace=True)
            da_temp = da_temp.sort_index().loc[:(self.pivot_date+dt.timedelta(hours=23))].copy()
            last_date = da_temp.index[-1] + pd.Timedelta(days=1)

            # Step 2: Add this new timestamp to the DataFrame
            da_temp.loc[last_date] = da_temp.iloc[-1]
            da_temp = da_temp.resample('h').ffill().iloc[:-1].copy()
            today_date = pd.to_datetime(dt.date.today())
            file_path = '//192.168.10.91/data/LiveScreen_v01.xlsx' # Replace with the path to your file
            last_modified_time = os.path.getmtime(file_path)
            modification_time = pd.to_datetime(dt.date.fromtimestamp(last_modified_time))
            if self.pivot_date == today_date:
                if modification_time != today_date:
                    raise Exception('File not updated')
                else:
                    gas_act = pd.read_excel(file_path, sheet_name='gas_main')
                    gas_act.columns = ['product', 'tenor', 'bid', 'offer']
                    gas_act = gas_act.iloc[1:].copy()
                    gas_act['product'] = gas_act['product'].ffill()
                    gas_act['mid'] = gas_act[['bid', 'offer']].mean(axis=1)
                    gas_da = gas_act.loc[gas_act['product']=='DA']['mid'].copy()
                    gas_da.name = 'ttf'
                    gas_da.index = [self.pivot_date + dt.timedelta(days=1)]
                    da_temp = pd.concat([da_temp, gas_da]).resample('h').bfill().iloc[:-1].copy()
            self.da_data[market] = da_temp.copy()
                