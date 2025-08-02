"""
    Prices of fuels, power and euas
    
    Need to handle both fut curves and day ahead data
        for train and analysis
        
    Common methods will be:
        creating futures curve
        creating spot day ahead data
"""


import pandas as pd
import numpy as np
import datetime as dt
from copy import deepcopy
from fund_analysis.utils import ENUMS as enums
from .input_data import InputData as input_data
from Utilities.date_functions import start_date, end_date
import statsmodels.api as sm

class Coal(input_data):
    fut_matrix = {}
    data_curve = {}
    da_data = {}
    
    def __init__(self, params_dict, coal_markets=[]):
        super().__init__(params_dict=params_dict)
        self._coal_markets = ['api2']
        self.fut_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        
        
    @property
    def coal_markets(self):
        return self._coal_markets
        
    def reset_variables(self):
        self.start_date_list = []
        self.end_date_list = []
        self.data_curve = {}
        
    def reset_data(self):
        self.fut_matrix = {}
        self.data_curve = {}
        self.da_data = {}
        
    def get_fut_matrix(self):
        for market in self.coal_markets:
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
            
    @staticmethod
    def extrapolate_coal_prices(market_df, gas_curve, gas_da, new_date, da_data):
        gas_curve = gas_curve.interpolate()
        gas_da = gas_da.resample('D').mean()
        # Get the last 30 rows starting from the second last day of both DataFrames
        market_last_30 = market_df.iloc[-30:]
        market_da_last_30 = da_data.iloc[-30:]
        gas_last_30 = gas_curve.iloc[-31:-1]
        gas_da_last_30 = gas_da.iloc[-31:-1]

        # Convert data to numeric to avoid dtype issues
        market_last_30 = market_last_30.apply(pd.to_numeric, errors='coerce')
        market_da_last_30 = market_da_last_30.apply(pd.to_numeric, errors='coerce')
        gas_last_30 = gas_last_30.apply(pd.to_numeric, errors='coerce')
        gas_da_last_30 = gas_da_last_30.apply(pd.to_numeric, errors='coerce')

        # Prepare the last row for the new date
        new_row = pd.Series(index=market_df.columns, name=new_date, dtype=float)

        # Regress the first column of market_df on gas_da
        y_first = market_da_last_30
        x_first = sm.add_constant(gas_da_last_30)  # Add a constant term for the regression
        model_first = sm.OLS(y_first.values, x_first.values).fit()
        x_new_first = pd.DataFrame([[1, gas_da.iloc[-1]]], columns=x_first.columns)
        pred = model_first.predict(x_new_first)[0]
        new_row.iloc[0] = pred.iloc[0]
        da_data = pd.concat([da_data, pd.DataFrame([[pred.iloc[0]]], columns=da_data.columns, index=[new_date + dt.timedelta(days=1)])])
        da_data = da_data.resample('h').bfill().iloc[:-1]

        # Iterate over each remaining column of market_df and regress it against the shifted gas_curve columns
        for i in range(1, len(market_df.columns)):
            # Set market_df column as the dependent variable (Y)
            y = market_last_30.iloc[:, i]
            
            # Set the previous column of gas_curve as the independent variable (X)
            x = gas_last_30.iloc[:, i - 1]
            x = sm.add_constant(x)

            # Fit the regression model
            model = sm.OLS(y.values, x.values).fit()

            # Use the fitted model to predict the value for the last row of gas_curve
            x_new = pd.DataFrame([[1, gas_curve.iloc[-1, i - 1]]], columns=x.columns)
            new_row.iloc[i] = model.predict(x_new)[0]

        # Append the new row to market_df
        market_df = pd.concat([market_df, pd.DataFrame([new_row])])

        return market_df, da_data

    
    def get_curve(self, gas_curve: dict = None,
                    gas_da: dict = None):
        self.get_fut_matrix()
        for market, market_df in self.fut_matrix.items():
            if not market in self.da_data:
                    self.get_da_data()
            market_df = market_df.interpolate()
            if not market in self.data_curve:
                # Step 1: Create the initial `curve` for the market starting from `self.pivot_date`.
                if self.pivot_date in market_df.index:
                    curve = market_df.loc[self.pivot_date, :].copy()
                else:
                    curve, da_data = self.extrapolate_coal_prices(market_df,
                                                        gas_curve['ttf'],
                                                        gas_da['ttf'],
                                                        self.pivot_date,
                                                        self.da_data['api2'])
                    self.da_data['api2'] = da_data
                    curve = curve.loc[self.pivot_date, :].copy()
                # Remove '_base' from the index names
                curve = curve.loc['M_2':].copy()
                curve.index = [f"{a.split('_')[0]}_{int(a.split('_')[1])-1}"
                                for a in curve.index]
                # Create a list of start dates for the curve index (replace your logic accordingly)
                dates_list = [start_date(self.pivot_date, product)
                            if product.lower() not in ['wk', 'wknd'] else
                            start_date(self.pivot_date, 'w') if product.lower() in ['wk'] else None
                            for product in curve.index]
                # Set the curve index to these calculated dates
                curve.index = dates_list
                # Step 2: Get the DA (day-ahead) value
                
                # Assuming da is just a single value
                da_value = self.da_data[market].ffill().loc[self.pivot_date]
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
        def estimate_spot_price(df, bom, front_month):
            """
            Estimate the daily spot price of coal based on the balance of the month (bom)
            and front month futures price (front_month).

            Parameters:
            df (pandas.DataFrame): DataFrame with 'bom' and 'front_month' columns.

            Returns:
            pandas.Series: Estimated daily spot prices.
            """
            # Number of days in the current month
            days_in_month = pd.to_datetime(df.index[-1]).days_in_month

            # Calculate weights for each day
            df['day_of_month'] = df.index.day
            df['bom_weight'] = df['day_of_month'] / days_in_month
            df['front_month_weight'] = 1 - df['bom_weight']

            # Estimate spot price
            df['estimated_spot'] = (df[bom] * df['bom_weight']) + (df[front_month] * df['front_month_weight'])
            
            return df['estimated_spot']
        
        self.get_fut_matrix()
        for market in self.coal_markets:
            if not market in self.da_data:
                temp_matrix = self.fut_matrix[market].copy()
                temp_matrix = temp_matrix[['M_1', 'M_2']].copy()
                spot_coal = estimate_spot_price(temp_matrix,
                                                'M_1', 'M_2')
                spot_coal.name = 'api2'
                temp = pd.DataFrame(spot_coal).sort_index().loc[:(self.pivot_date+dt.timedelta(hours=23))].copy()
                last_date = temp.index[-1] + pd.Timedelta(days=1)

                # Step 2: Add this new timestamp to the DataFrame
                temp.loc[last_date] = temp.iloc[-1]
                self.da_data[market] = temp.resample('h').ffill().iloc[:-1].copy()