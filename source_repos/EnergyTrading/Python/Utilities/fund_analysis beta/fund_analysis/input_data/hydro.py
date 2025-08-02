"""
Sobclass for Consumption
"""

from .external_fund_data import ExternalFundData as external_fund_data
import pandas as pd
import datetime as dt
import numpy as np


class Hydro(external_fund_data):
    
    def __init__(self, params_dict, fund_type='INF',
                    normalize_bool=False, ec_type='00'):
        super().__init__(params_dict, normalize_bool, ec_type)
        self._fund_type = fund_type
        self.unique_markets_list = ['at', 'fr']
    
    @property
    def fund_type(self):
        return self._fund_type
    
    def get_month_data(self):
        for market in self.unique_markets:
            if market not in self.month_fund_data:
                self.month_fund_data[market] = self.mid_fund_data[market]
                self.month_fund_data[market].drop(self.month_fund_data[market].index,
                                                    inplace=True)
    
    def get_normal_data(self):
            for market in self.unique_markets:
                if market not in self.normal_fund_data:
                    normal = self.data_loader.get_fund_raw_data('normal',
                                                                self.fund_type,
                                                                self.ec_type,
                                                                market).set_index('value_date')
                    # Start end for new df
                    last_date = normal.index[-1]
                    start_date = last_date + dt.timedelta(days=1)
                    end_date = start_date + dt.timedelta(weeks=52*5)
                    new_index = pd.date_range(start=start_date,
                                            end=end_date)
                    new_normal = pd.concat([normal,
                                            pd.DataFrame(index=new_index, columns=normal.columns)])
                    # Get daily averages
                    # Ensure datetime index
                    assert isinstance(normal.index, pd.DatetimeIndex), "Index of 'normal' must be a DatetimeIndex"
                    assert isinstance(new_normal.index, pd.DatetimeIndex), "Index of 'new_normal' must be a DatetimeIndex"

                    # Compute daily means
                    norm_daily = normal.copy()
                    norm_daily['day'] = norm_daily.index.day_of_year
                    daily_means = norm_daily.groupby('day')['INF'].mean()

                    # Map daily means to new_normal
                    new_normal['day'] = new_normal.index.day_of_year
                    new_normal['mean'] = new_normal['day'].map(daily_means)

                    # Fill missing values
                    new_normal['INF'] = new_normal['INF'].fillna(new_normal['mean'])

                    self.normal_fund_data[market] = new_normal[['INF']].copy()
                    del new_normal
                    
        
    def get_fund_data(self):
        """
        Operate with self.fund_type from subclass
        """
        self.transform_and_update_params_dict()
        # Get first and last period to know the curve span
        self.get_curve_start_end_date
        if self.fut_periods is None:
            self.fut_periods = self.get_futures_periods()
        # Call fcst_types based on fut_periods
        # Mid forecast as default
        self.get_mid_data()
        # Get the length of mid forecasts
        temp_mid = self.mid_fund_data[list(self.mid_fund_data)[0]].copy()
        temp_mid['periods_forward'] = (temp_mid['value_date'] - temp_mid['forecast_date']).dt.total_seconds() / 3600        
        if max(temp_mid['periods_forward'])<self.fut_periods:
            self.get_normal_data()
                
        if self.normalize_bool:
            self.get_normal_data()
    
    def get_curve(self):
        self.get_data_matrix()
        for market in self.unique_markets:
            curve = self.mid_fund_matrix[market].loc[self.pivot_date].dropna().copy()
            if len(curve) <= self.fut_periods / 24:
                curve.index = self.pivot_date + pd.to_timedelta(curve.index, unit='h')
                last_value = self.pivot_date + pd.to_timedelta(self.fut_periods, unit='h')
                normal_curve = self.normal_fund_data[market].copy()
                normal_curve = normal_curve.loc[curve.index[-1]:last_value].copy()
                curve = curve.combine_first(normal_curve.iloc[:, 0])
                curve.loc[curve.index[-1] + dt.timedelta(days=1)] = np.nan

                curve = curve.resample('h', closed='left').ffill().iloc[:-1].copy()
                if len(curve) < self.fut_periods:
                    last_year_curve = curve.loc[curve.index.year == curve.index.year.max()].copy()
                    periods_diff = self.fut_periods - len(curve)
                    years_to_add = int((periods_diff - 1) // 8760) + 1
                    base_year = int(last_year_curve.index.year.max())
                    for year in range(1, years_to_add + 1):
                        # Create a new index by updating the year for each timestamp in the last year's index
                        new_index = last_year_curve.index.map(lambda dt: dt.replace(year=base_year + year))

                        # Create a new Series with the values from the last year's data but with the updated index
                        new_data = pd.Series(data=last_year_curve.values, index=new_index)

                        # Concatenate the original curve with the newly created future curve
                        curve = pd.concat([curve, new_data])
                self.data_curve[market] = pd.DataFrame(curve).resample('h').ffill().rename(columns={curve.name: self.fund_type})
            else:
                curve = curve.loc[:self.fut_periods].copy()
                curve.index = self.pivot_date + pd.to_timedelta(curve.index, unit='h')
                self.data_curve[market] = pd.DataFrame(curve).resample('h').ffill().rename(columns={curve.name: self.fund_type}).resample('h').ffill()

            if self.normalize_bool:
                norm_curve = self.normal_fund_data[market].loc[self.data_curve[market].index[0]:self.data_curve[market].index[-1]].resample('h').ffill().copy()
                norm_curve.loc[norm_curve.index[-1] + dt.timedelta(days=1)] = np.nan
                norm_curve = norm_curve.resample('h', closed='left').ffill().iloc[:-1].copy()

                if len(norm_curve) < self.fut_periods:
                    last_year_curve = norm_curve.loc[norm_curve.index.year == norm_curve.index.year.max()].copy()
                    periods_diff = len(self.data_curve[market]) - len(norm_curve)
                    years_to_add = int((periods_diff - 1) // 8760) + 1
                    base_year = int(last_year_curve.index.year.max())
                    for year in range(1, years_to_add + 1):
                        # Create a new index by updating the year for each timestamp in the last year's index
                        new_index = last_year_curve.index.map(lambda dt: dt.replace(year=base_year + year))

                        # Create a new Series with the values from the last year's data but with the updated index
                        new_data = pd.Series(data=last_year_curve.values.flatten(), index=new_index, name=last_year_curve.columns[0])

                        # Concatenate the original curve with the newly created future curve
                        norm_curve = pd.concat([norm_curve, new_data])

                # Calculate the normalized curve
                self.data_curve_normalized[market] = self.data_curve[market] / norm_curve
            
    def get_da_data(self):
        super().get_da_data()
        for market, market_df in self.da_data.items():
            last_date = market_df.index[-1] + pd.Timedelta(days=1)

            # Step 2: Add this new timestamp to the DataFrame
            market_df.loc[last_date] = market_df.iloc[-1]
            self.da_data[market] = market_df.resample('h').ffill().iloc[:-1].copy()
        if self.normalize_bool:
            for market, market_df in self.da_data_normalized.items():
                self.da_data_normalized[market] = market_df.resample('h').ffill().copy()