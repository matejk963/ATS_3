# -*- coding: utf-8 -*-
"""
Created on Sun Jan 14 10:42:29 2024

@author: krajcovic
"""

import pandas as pd
from pandas.tseries.offsets import DateOffset
import numpy as np
from scipy.stats import kurtosis, skew
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.dates import MO

from datetime import datetime, timedelta
import seaborn as sns

import datetime as dt
import os
from Database.TPData import TPDataAssembly as TDA
from Loaders.DataLoader_class import DataLoader as DL
from Database.DB_reader import Database
from Loaders.EikonSpot_class import EikonSpot as ES
from Loaders.EikonFut_class import EikonFut as EF
from Loaders.RLD_fetch import RLDDatabaseData
from Loaders.DataLoader_class import DataLoader as DL

"""

"""  


class RldMonitor:
    
    def __init__(self, country='de',
                 config=r"Z:\EnergyTrading\configDB.json"):
        self._country = country
        self._sD = None
        self._eD = None
        self._db_inst = RLDDatabaseData(config)
        # self._dataload_inst = None
        
        
        
    @property
    def db_inst(self):
        return self._db_inst
    
    
    @property
    def dataloader_inst(self):
        if hasattr(self, '_dataloader_inst'):
            return self._dataloader_inst
        else:
            self._dataloader_inst = DL(self.sD, self.eD, {}, {})
            return self._dataloader_inst
        
    @property
    def sD(self):
        if self._sD is not None:
            return self._sD
        else:
            raise ValueError('Need to specify start date')
    @property
    def eD(self):
        if self._sD is not None:
            return self._eD
        else:
            raise ValueError('Need to specify end date')
            
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
            
    def get_raw_data(self,market='de', source='db'):

        if source in ['db']:
            
                    
            fct = self.dataloader_inst.get_RLD_raw_fcst(country='de').sort_values(['value_date'])
            norm = self.dataloader_inst.get_RLD_raw_normal(country='de').sort_values(['value_date'])
            norm = norm.drop_duplicates(['value_date', 'wind', 'solar', 'con'])
            df = fct.merge(norm[['value_date', 'wind', 'solar', 'con']], on='value_date', how='inner')

            return df
        else:
            fct = self._db_inst.history_live_merge(from_=self.sD,
                                                  to_=self.eD)
            norm = self.dataloader_inst.get_RLD_raw_normal(country=market).sort_values(['value_date'])
            norm = norm.drop_duplicates(['value_date', 'wind', 'solar', 'con'])
            df = fct.merge(norm[['value_date', 'wind', 'solar', 'con']], on='value_date', how='inner')
            return df
    
    def process_data(self, df, fct_type=0):
        out_df = df[df['forecast_date'].dt.hour==fct_type].copy()
        out_df = out_df.loc[((out_df['forecast_date']>=self.sD)&
                             (out_df['forecast_date']<=self.eD))].copy()
        out_df['rld'] = out_df['con_ens'] - out_df['wind_ens'] - out_df['solar_ens']
        if ('con' and 'wind' and 'solar') in out_df.columns:
            out_df['rld_n'] = out_df['con'] - out_df['wind'] - out_df['solar']
            out_df['rld'] = out_df['rld']/out_df['rld_n']
        out_df = out_df[['forecast_date', 'value_date', 'rld']].copy()
        out_df['hours'] = (out_df['value_date'] - out_df['forecast_date']).dt.total_seconds()/3600
        out_df['rld'] = out_df['rld'].fillna(method='ffill')
        out_df = out_df.loc[((out_df['hours']>23)&
                             (out_df['hours']<360))].copy()

        out_df = pd.pivot_table(data=out_df, index=['forecast_date'], columns=['hours'], values=['rld'])
        out_df = out_df.fillna(method='ffill', axis=1)
        out_df.columns = out_df.columns.droplevel(0)
        return out_df
    
    """
    Here define the mask a.k.a. shape of collecting the data from main matrix
    'row_behind' variable means how many day aheads will be look for in analyzing
    the data
    """
    @property
    def da_lookback(self):
        if hasattr(self, '_da_lookback'):
            return self._da_lookback
        else:
            raise ValueError('Set Day ahead lookback days')
            
    def set_da_lookback(self, da_lookback):
        self._da_lookback = da_lookback
    
    
           
    
    def mask(self, df, stat_type):
        row_behind = self.da_lookback
        mask1 = np.zeros((row_behind,df.shape[1]), dtype=bool)
        mask1[:,:24] = True
        mask2 = np.zeros((1,df.shape[1]),dtype=bool)
        mask2[:,:] = True
        mask = np.concatenate((mask1, mask2))
        if stat_type == 'full':
            return mask
        elif stat_type == 'hist':
            return mask1
        elif stat_type == 'fcst':
            return mask2
    
    @staticmethod
    def get_da_data(df):
        out_df = df.unstack().reset_index()
        out_df['value_date'] = out_df['forecast_date'] + pd.to_timedelta(out_df['hours'], unit='h')
        out_df = out_df.sort_values('value_date')
        out_df = out_df.loc[((out_df['hours']>23)&
                             (out_df['hours']<48))].copy()
        out_df = out_df[['value_date', 0]].copy()
        return out_df
    
    @staticmethod
    def apply_mask(row_idx, arr, mask):
        # Determine start and end index for slicing
        start_idx = max(0, row_idx - mask.shape[0]+1)
        end_idx = row_idx + 1

        # Adjust mask size if near start of array
        mask_adjusted = mask[-(end_idx - start_idx):]

        # Apply mask to the selected part of the array
        selected_data = arr[start_idx:end_idx][mask_adjusted]

        # Return the selected data
        return selected_data
    
    # Statics to compute
    def dist_mean(self, row_idx, arr, mask):
        sel_data = self.apply_mask(row_idx, arr, mask)
        return np.nanmean(sel_data)
    
    def dist_std(self, row_idx, arr, mask):
        sel_data = self.apply_mask(row_idx, arr, mask)
        return np.nanstd(sel_data)
    
    def dist_kurt(self, row_idx, arr, mask):
        sel_data = self.apply_mask(row_idx, arr, mask)
        return kurtosis(sel_data)
    
    def dist_skew(self, row_idx, arr, mask):
        sel_data = self.apply_mask(row_idx, arr, mask)
        return skew(sel_data)
    
    def assemble_stat(self, df, stat_type='full'):
        mask = self.mask(df, stat_type)
        arr = np.array(df)

        # Compute statistics for each row
        mean = pd.DataFrame([self.dist_mean(i, arr, mask) for i in range(arr.shape[0])],
                            columns=['mean'],
                            index=df.index)
        std = pd.DataFrame([self.dist_std(i, arr, mask) for i in range(arr.shape[0])],
                            columns=['std'],
                            index=df.index)
        kurt = pd.DataFrame([self.dist_kurt(i, arr, mask) for i in range(arr.shape[0])],
                            columns=['kurt'],
                            index=df.index)
        skew = pd.DataFrame([self.dist_skew(i, arr, mask) for i in range(arr.shape[0])],
                            columns=['skew'],
                            index=df.index)

        # Concatenate the statistics DataFrames
        out_df = pd.concat([mean, std, kurt, skew], axis=1, join='inner')

        # Calculate overall statistics for each metric
        for stat in ['mean', 'std', 'kurt', 'skew']:
            out_df[f'{stat}_mean'] = out_df[stat].mean()
            out_df[f'{stat}_90th'] = out_df[stat].quantile(0.9)
            out_df[f'{stat}_75th'] = out_df[stat].quantile(0.75)
            out_df[f'{stat}_25th'] = out_df[stat].quantile(0.25)
            out_df[f'{stat}_10th'] = out_df[stat].quantile(0.1)

        return out_df
    
    
    def plot_stats(self, df):
        # Compute stats for 'hist' and 'fcst'
        hist_stats = self.assemble_stat(df, 'hist')
        fcst_stats = self.assemble_stat(df, 'fcst')
        
        # Calculate 1st and 5th quantiles for 'mean', 'std', and 'skew'
        quantiles = [0.2, 0.8]  # Adjust if you meant different quantiles for 1st and 5th
        mean_quantiles = hist_stats['mean'].quantile(quantiles)
        std_quantiles = hist_stats['std'].quantile(quantiles)
        skew_quantiles = hist_stats['skew'].quantile(quantiles)
        
        # Identify dates where all moments are in the 1st or 5th quantile
        extreme_dates = hist_stats[(hist_stats['mean'].le(mean_quantiles[0.2]) | hist_stats['mean'].ge(mean_quantiles[0.8])) &
                                   (hist_stats['std'].le(std_quantiles[0.2]) | hist_stats['std'].ge(std_quantiles[0.8])) &
                                   (hist_stats['skew'].le(skew_quantiles[0.2]) | hist_stats['skew'].ge(skew_quantiles[0.8]))].index

        
        last_date = fcst_stats.index.max() 
        num_new_rows = 13         
        
        new_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=num_new_rows, freq='D')
        
        # Create a new DataFrame with these dates as the index
        # Assuming df has columns 'A', 'B', 'C', etc., initialize them with NaN or a default value
        new_df = pd.DataFrame(index=new_dates, columns=fcst_stats.columns)  # Replace df.columns with actual column names if needed
        
        # Concatenate the new DataFrame with the original DataFrame
        fcst_stats = pd.concat([fcst_stats, new_df])
        

        # Merge the hist and shifted fcst dataframes
        merged_stats = hist_stats.merge(fcst_stats, left_index=True,
                                        right_index=True,
                                        how='left',
                                        suffixes=('_hist', '_fcst'))

        # Create a 2x2 subplot grid with shared x-axis
        fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharex=True)
        fig.suptitle('Statistical Moments for Hist and Fcst')

        # Define moments and titles for subplots
        moments = ['mean', 'std', 'kurt', 'skew']
        titles = ['Mean', 'Standard Deviation', 'Kurtosis', 'Skewness']

        # Plotting each moment
        for i, moment in enumerate(moments):
            ax = axes[i//2, i%2]

            # Plot 'hist' and 'fcst' for each moment
            ax.plot(merged_stats.index, merged_stats[f'{moment}_hist'], label=f'Hist {moment}')
            ax.plot(merged_stats.index, merged_stats[f'{moment}_fcst'], label=f'Fcst {moment} (shifted)', linestyle='--')
            
            # Add mean, 90th and 10th percentile lines for 'hist'
            if moment in ['mean', 'std', 'kurt', 'skew']:
                ax.axhline(hist_stats[f'{moment}_mean'].iloc[0], color='red', linestyle='-', label='Hist Mean')
                ax.axhline(hist_stats[f'{moment}_75th'].iloc[0], color='green', linestyle='-', label='Hist 75th Percentile')
                ax.axhline(hist_stats[f'{moment}_25th'].iloc[0], color='blue', linestyle='-', label='Hist 25th Percentile')
            # Add vertical lines for extreme dates
            for date in extreme_dates:
                ax.axvline(date, color='magenta', linestyle='--', alpha=0.7)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.show()

    
    

    

    
        
    
    
    
    
class SettleMonitor:
    
    """
    Class for monitoring settlement prices of power and power fuels
    Default gas is TTF
    Default coal is API2
    """
    
    def __init__(self):
        self._grids_list = None
        self._sD = None
        self._eD = None
        # self._gas = gas
    
    
    # @property
    # def gas(self):
    #     return self._gas
    
    # def change_gas(self, new_gas):
    #     self._gas = new_gas
    
    @property
    def sD(self):
        if self._sD is not None:
            return self._sD
        else:
            raise ValueError('Need to specify start date')
    @property
    def eD(self):
        if self._sD is not None:
            return self._eD
        else:
            raise ValueError('Need to specify end date')
    @property
    def grid_list(self):
        if self._grid_list is not None:
            return self._grid_list
        else:
            raise ValueError('Need to specify grid_list')
            
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
    def set_grids(self, grid_list):
        self._grid_list = grid_list
    
    @staticmethod
    def fill_weekends(out_df):
        # Generate a full date range from the start to the end of the provided data
        full_date_range = pd.date_range(start=out_df.index.min(),
                                        end=out_df.index.max())
        
        # Reindex the DataFrame to include all dates in the range, filling missing values
        out_df = out_df.reindex(full_date_range).fillna(method='ffill')
        return out_df
        
        
    def get_power_spot(self):
        
        db_reader = Database()
        df_spot = db_reader.getSpotPriceData(listOfMarkets=self.grid_list,
                                             _from=self.sD.strftime('%Y-%m-%d'),
                                             _to=self.eD.strftime('%Y-%m-%d'))
        return df_spot
    
    
    
    def get_gas_spot(self):
        ef_inst = EF('gas_da')
        out_df = ef_inst.gas_da_df(self.sD, self.eD)
        out_df = self.fill_weekends(out_df)
        out_df.index.name = 'date'
        return out_df
    
    def get_eua_df(self):
        ef_inst = EF('eua')
        
        product_list = ['Y_1']
        year_list = [None]
        delivery_list = ['base']
        
        df = ef_inst.fwd_df(self.sD, self.eD,
                            product_list, delivery_list, year_list)
        df.columns = ['eua']
        df = pd.DataFrame(self.fill_weekends(df),columns=['eua'])
        df.index.name = 'date'
        return df
    
    def get_coal_spot(self):
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
        product_list = ['M_0', 'M_1']
        delivery_list = ['base'] * len(product_list)
        year_list = [None] * len(product_list)
        ef_inst = EF('coal')
        coal_df = ef_inst.fwd_df(self.sD, self.eD,
                                 product_list,
                                 delivery_list,
                                 year_list)
        bom, front_month = coal_df.columns
        coal_df['spot_coal'] = estimate_spot_price(coal_df, bom, front_month)
        coal_spot = self.fill_weekends(coal_df[['spot_coal']].copy())
        coal_spot.index.name = 'date'
        return coal_spot
    
    @staticmethod
    def aggregate_by_time(df, tenor, dist=False):
        if tenor in ['m', 'M']:
            df_m = df.resample('ME').mean()
        elif tenor in ['q', 'Q']:
            df_m = df.resample('QE').mean()
        elif tenor in ['y', 'Y']:
            df_m = df.resample('YE').mean()
        if dist:
            return df_m, df
        else:
            return df_m
    
    def power_liq(self, product, delivery='base', dist=False):
        tenor, period = product.split('_')
        if not hasattr(self, 'power'):
            self.power = self.get_power_spot()
        power = self.power.copy()
        if delivery in ['peak']:
            power['hour'] = power.index.hour
            power['weekday'] = power.index.weekday
            power['peak'] = np.where(((power['hour']>7)&
                                      (power['hour']<20)&
                                      (power['weekday']<5)),1,0)
            power = power.loc[power['peak']==1].drop(['peak', 'hour', 'weekday'],axis=1).copy()
        
        
        return self.aggregate_product(power, tenor, int(period))
    
    @staticmethod
    def aggregate_product(data, period, period_number):
        """
        Aggregate a single-column DataFrame by the specified period using its datetime index and select data for a specific period number.
        
        Parameters:
        - data: DataFrame with a datetime index and a single column.
        - period: The period to aggregate by ('W', 'M', 'Q', 'Y').
        - period_number: The specific period number to select (e.g., 3rd week, 4th month).
        
        Returns:
        - A DataFrame aggregated and filtered according to the specified criteria.
        """
        
        # Resample and aggregate
        if period.upper() == 'W':
            resampled = data.resample('W').mean()
            # Filter by the specific week number within the year
            selection = resampled[resampled.index.isocalendar().week == period_number]
        elif period.upper() == 'M':
            resampled = data.resample('M').mean()
            # Filter by the specific month
            selection = resampled[resampled.index.month == period_number]
        elif period.upper() == 'Q':
            resampled = data.resample('Q').mean()
            # Filter by the specific quarter
            selection = resampled[resampled.index.quarter == period_number]
        elif period.upper() == 'Y':
            resampled = data.resample('Y').mean()
            # For yearly aggregation, "period_number" might not apply as directly
            selection = resampled if period_number == 'all' else resampled[resampled.index.year == period_number]
        else:
            raise ValueError("Invalid period specified. Choose 'W', 'M', 'Q', or 'Y'.")
    
        return selection
    
    @staticmethod
    def calculate_difference(df1, df2, spread_type):
        """
        Calculate the difference between two DataFrames for matching periods.
        
        Parameters:
        - df1: DataFrame 1 (minuend).
        - df2: DataFrame 2 (subtrahend).
        
        Returns:
        - A new DataFrame containing the difference between the two input DataFrames.
        """
        def sum_by_pairs_or_leave(data, spread_type):
            """
            Sum data by pairs (odd + even rows) or leave it as is.
            
            Parameters:
            - data: DataFrame containing the data.
            - choice: 'sum_pairs' to sum by pairs, 'leave' to leave the data unchanged.
            
            Returns:
            - A new DataFrame with data summed by pairs or left unchanged.
            """
            if spread_type == 'intramarket':
                # Ensure the DataFrame is reset to use default integer index for pairing
                data = data.reset_index()
                summed_data = []
                
                for i in range(0, len(data), 2):
                    # Sum current and next row if next row exists, else just take the current row's value
                    sum_value = data.iloc[i]['de'] + data.iloc[i+1]['de'] if i+1 < len(data) else data.iloc[i]['de']
                    summed_data.append(sum_value)
                
                # Create a new DataFrame with the summed values
                # Reuse the datetime index from the original DataFrame for every pair
                result_index = data.iloc[range(0, len(data), 2)]['datetime']
                result = pd.DataFrame(summed_data, index=result_index, columns=['de_summed'])
                
            elif spread_type == 'intermarket':
                # Leave the data unchanged
                result = data
                
            else:
                raise ValueError("Invalid choice. Use 'sum_pairs' or 'leave'.")
            
            return result
        # Ensure that the indexes are aligned before subtraction
        # This step is crucial if there's a possibility of missing periods in either DataFrame
        df1_aligned, df2_aligned = df1.align(df2, join='outer', fill_value=0)
        
        # Calculate the difference
        difference = df1_aligned - df2_aligned
        difference = sum_by_pairs_or_leave(difference, spread_type)
        
        return difference
            
    def process_spread(self, spread_list, delivery='base', spread_type='intramarket'):
        product1, product2 = spread_list
        leg1 = self.power_liq(product1)
        leg2 = self.power_liq(product2)
        
        # spread = pd.concat([leg1, leg2],join='outer').sort_index()
        spread = self.calculate_difference(leg1, leg2, spread_type)
        # spread['year'] = spread.index.year
        # spread = spread.groupby('year').diff()
        return spread

    
    # def liq_spread(self, spread_list, delivery='base', dist=False):
        
    #     if dist:
    #         power_m, power = self.power_liq(product, delivery, dist)
    #         self.plot_histogram(power)
    #         return power_m
    #     else:
    #         return self.power_liq(product, delivery, dist)
            
        
            
    
    @staticmethod
    def plot_histograms(df):
        
        def add_percentiles_to_plot(series):
            percentiles = [10, 25, 50, 75, 90]
            percentile_values = np.percentile(series, percentiles)
            colors = ['red', 'green', 'blue', 'cyan', 'magenta']
            labels = ['10th', '25th', 'Mean', '75th', '90th']
            
            for percentile, value, color, label in zip(percentiles, percentile_values, colors, labels):
                if percentile == 50:  # Mean
                    mean_value = series.mean()
                    plt.axvline(x=mean_value, color=color, label=f'{label}: {mean_value:.2f}')
                else:
                    plt.axvline(x=value, color=color, label=f'{label}: {value:.2f}')
        # Plot histogram for all data
        plt.figure(figsize=(10, 6))
        df['price'].hist(bins=30, alpha=0.7)
        plt.title('Histogram for All Data')
        add_percentiles_to_plot(df['price'])
        plt.legend()
        plt.show()
        
        # Plot histograms for each year
        years = df.index.year.unique()
        for year in years:
            plt.figure(figsize=(10, 6))
            year_data = df[df.index.year == year]
            year_data['price'].hist(bins=30, alpha=0.7)
            plt.title(f'Histogram for {year}')
            add_percentiles_to_plot(year_data['price'])
            plt.legend()
            plt.show()
    
    
    
        # plot_histograms(prices)
        
        
    
class FuturesMonitor:
    
    def __init__(self):
        self._spot_inst = SettleMonitor()
        self._ef_inst = None
        
    @property
    def spot_inst(self):
        return self._spot_inst    
    
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
    def set_market(self, market):
        self._market = market
        
    @property
    def market(self):
        return self._market
    @property
    def sD(self):
        return self._sD
    @property
    def market(self):
        return self._eD
    
            
    
    def get_power(self, product_list, delivery_list, year_list):
        return EF(market=self.market,
                  cont=self.cont).fwd_df(self.sD, self.eD,
                                 product_list,
                                 delivery_list,
                                 year_list)
                                         
                                         
                                         
    def get_spread(self,spread):
        product_list
                                     
        
    
    
    
    

class TermStructure:
    
    def __init__(self, market='de'):
        self._market = market
        
    @property
    def market(self):
        return self._market
    
    
    def set_date(self, date=None):
        if hasattr(self, '_date') and (date in None):
            self._date = pd.to_datetime(dt.today().date)

class FuelSpreadsMonitor:
    
    def __init__(self, market, params_dict):
       
        self._ef_inst = None
        self._market = market
        self._params_dict = params_dict
        
    @property
    def market(self):
        return self._market
    
    @property
    def params_dict(self):
        return self._params_dict
    
    @property
    def product_list(self):
        return self.params_dict['product_list']
    
    @property
    def delivery_list(self):
        return self.params_dict['delivery_list']
    
    @property
    def year_list(self):
        return self.params_dict['year_list']
    
    @property
    def sD(self):
        return self.params_dict['sD']
    
    @property
    def eD(self):
        return self.params_dict['eD']
    
    @property
    def cont(self):
        return self.params_dict['cont']
    
    @property
    def ef_inst(self):
        if self._ef_inst is None:
            self._ef_inst = EF(market=self.market)
            
    def get_power(self):
        return EF(market=self.market, 
                  cont=self.cont).fwd_df(self.sD, self.eD,
                                 self.product_list,
                                 self.delivery_list,
                                 self.year_list)
    def get_gas(self):
        return EF(market='gas', 
                  cont=self.cont).fwd_df(self.sD, self.eD,
                                 self.product_list,
                                 ['base'] * len(self.product_list),
                                 self.year_list)
    
    def get_coal(self):
        return EF(market='coal', 
                  cont=self.cont).fwd_df(self.sD, self.eD,
                                 self.product_list,
                                 ['base'] * len(self.product_list),
                                 self.year_list)
    
    def get_eua(self):
        return EF(market='eua', 
                  cont=True).fwd_df(self.sD, self.eD,
                                 ['Y_1'],
                                 ['base'],
                                 [None])
        # eua.columns = ['eua']
        
    
    
    def get_data(self):
        self.power = self.get_power()
        self.gas = self.get_gas()
        self.coal = self.get_coal()
        self.eua = self.get_eua()
        self.eua = pd.concat([self.eua]*self.power.shape[1],axis=1)
        for a in [self.power, self.gas, self.coal, self.eua]:
            a.columns = self.product_list
        # self.power.columns
        # self.gas.columns = self.power.columns
        # self.coal.columns = self.power.columns
        # self.eua.columns = self.power.columns
    
    def get_css(self):
        if not hasattr(self, 'power'):
            self.get_data()
        css = self.power - 2*(self.gas+self.eua*0.2)
        css.columns = [a + '_css' for a in css.columns]
        # css.index
        ghr = self.power / (self.gas + self.eua*0.2)
        ghr.columns = [a + '_ghr' for a in ghr.columns]
        return css, ghr
    
    def get_cds(self):
        if not hasattr(self, 'power'):
            self.get_data()
        cds = self.power - (self.coal/6.15 + self.eua*0.35)/0.35
        cds.columns = [a + '_cds' for a in cds.columns]
        _chr = self.power / (self.coal/6.15 + self.eua*0.35)
        _chr.columns = [a + '_chr' for a in _chr.columns]
        return cds, _chr
    
    def get_mc_ratio(self):
        if not hasattr(self, 'power'):
            self.get_data()
        mc_ratio = (self.gas + self.eua*0.2)/(self.coal/6.15 + self.eua*0.35)
        mc_ratio.columns = [a + '_mc' for a in mc_ratio.columns]
        return mc_ratio
    
    # def get_spread(self, spread):
        
        
    def basic_monitor_plot(self):
        css, ghr = self.get_css()
        cds, chr1 = self.get_cds()
        mc_ratio = self.get_mc_ratio()
        
        df1, df2, df3, df4, df5 = css, ghr, cds, chr1, mc_ratio
        
        # Assuming all DataFrames have the same column names, let's get those names
        column_names = df1.columns.tolist()
        
        # We'll plot the first two columns in this example
        for col_name in column_names:  # Adjust slice as needed
            fig, axs = plt.subplots(2, 3, figsize=(15, 10))  # Creating a 2x3 grid of plots

            # Adjustments to leave space for titles or legends
            plt.subplots_adjust(hspace=0.3, wspace=0.3)
            
            # Plotting the first DataFrame in the first subplot
            axs[0, 0].plot(df1.index, df1[col_name], label=f'DF1 {col_name}')
            axs[0, 0].set_title(f'DF1 {col_name}')
            axs[0, 0].legend()
        
            # Plotting the second DataFrame in the second subplot
            axs[0, 1].plot(df2.index, df2[col_name], label=f'DF2 {col_name}')
            axs[0, 1].set_title(f'DF2 {col_name}')
            axs[0, 1].legend()
        
            # Plotting the third DataFrame in the first subplot of the second row
            axs[1, 0].plot(df3.index, df3[col_name], label=f'DF3 {col_name}')
            axs[1, 0].set_title(f'DF3 {col_name}')
            axs[1, 0].legend()
        
            # Plotting the fourth DataFrame and overlaying df5 in the second subplot of the second row
            axs[1, 1].plot(df4.index, df4[col_name], label=f'DF4 {col_name}')
            axs[1, 1].plot(df5.index, df5[col_name], label=f'DF5 {col_name}', linestyle='--')
            axs[1, 1].set_title(f'DF4 & DF5 {col_name}')
            axs[1, 1].legend()
        
            # Regplot of df4 vs df3
            sns.regplot(ax=axs[0, 2],data=df2.merge(df4, left_index=True, right_index=True,
                                                    how='inner', suffixes=('_ghr', '_chr')),
                        x=col_name + '_chr',
                        y=col_name + '_ghr', scatter_kws={'s': 10}, line_kws={"color": "red"})
            axs[0, 2].set_title(f'Regression of chr on ghr')
            
            # Regplot of df5 vs df4
            sns.regplot(ax=axs[1, 2],data=df5.merge(df4, left_index=True, right_index=True,
                                                    how='inner', suffixes=('_mc_ratio', '_chr')),
                        x=col_name + '_mc_ratio',
                        y=col_name + '_chr', scatter_kws={'s': 10}, line_kws={"color": "red"})
            axs[1, 2].set_title(f'Regression of DF5 on DF4\n{col_name}')
        
            plt.show()
        
if __name__ == '__main__':
    
    sD = dt.datetime(2015,1,1)
    eD = dt.datetime(2024,1,1)
    market ='de'
    
    mon_inst = SettleMonitor()
    mon_inst.set_date_range(sD, eD)
    mon_inst.set_grids(['de'])
    
    spread_list = ['Q_2', 'Q_3']
    spread = mon_inst.process_spread(spread_list, 'base')
    
    
    # params_dict = {'product_list': ['M.3', 'M.4', 'Q.2', 'Q.3', 'Q.4'],
    #  'delivery_list': ['base', 'base', 'base', 'base', 'base'],
    #  'year_list': [2017, 2017, 2017, 2017, 2017],
    #  'sD': dt.datetime(2016, 1, 1, 0, 0),
    #  'eD': dt.datetime(2017, 2, 8, 0, 0),
    #  'cont': False}
    
    # fsm_inst = FuelSpreadsMonitor('de', params_dict)
    
    # gas = fsm_inst.get_eua()
    
    # settle_o = SettleMonitor()
    
    # settle_o.set_grids('de')
    # settle_o.set_date_range(datetime(2023,1,1),
    #                         datetime(2024,2,1))
    
    # liq = settle_o.liq_spread(['M_1'])
    
    
#     import seaborn as sns
#     from Database.GenFetchClass import ENTSOEData as ED
    
    
#     params_dict = {}
    
#     params_dict['product_list'] = ['M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3', 'Y_1']
#     # params_dict['product_list'] = ['M.1', 'M,2', 'M.3', 'Q.2', 'Q.3', 'Q.4', 'Y.1']
#     params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
#     params_dict['year_list'] = [2023] * len(params_dict['product_list'])

#     params_dict['sD'] = datetime(2022,6,1)
#     params_dict['eD'] = datetime(2023,1,1)
    
#     params_dict['sD'] = datetime(2023,10,1)
#     params_dict['eD'] = datetime(2024,2,5)
    
#     entsoe = ED()
#     entsoe.set_api_key("4961d306-7fb4-410a-9bb0-165a59343d92")
#     entsoe.set_country("DE")
#     entsoe.set_date_range(params_dict['sD'], params_dict['eD'])
    
#     de_gen = entsoe.get_generation_data()
#     de_gen = de_gen.resample('D').mean()
#     de_gen = de_gen.drop(['Wind Offshore', 'Wind Onshore', 'Solar'],axis=1)
#     de_gen['rld'] = de_gen.sum(axis=1)
#     de_gen['gas_perc'] = de_gen['Fossil Gas']/de_gen['rld']

    
#     entsoe.set_country("FR")
#     fr_gen = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Gen\FR_gen.csv',
#                          parse_dates=['datetime'], index_col=['datetime'])
#     fr_gen = fr_gen.resample('D').mean()
#     fr_gen.columns = [a + '_fr' for a in fr_gen.columns]
    
#     css_inst = FuelSpreadsMonitor('de', params_dict)
    
#     css_inst.basic_monitor_plot()
    
#     css, ghr = css_inst.get_css()
#     css.columns = [a + '_css' for a in css.columns]
#     mc_ratio = css_inst.get_mc_ratio()
#     mc_ratio.columns = [a + '_mc' for a in mc_ratio.columns]
    
        
    
#     spot_inst = SettleMonitor()
#     spot_inst.set_date_range(params_dict['sD'],
#                              params_dict['eD'])
#     spot_inst.set_grids(['de'])
#     power_spot = spot_inst.get_power_spot()
#     gas_spot = spot_inst.get_gas_spot()
#     eua_spot = spot_inst.get_eua_df()
#     coal_spot = spot_inst.get_coal_spot()
#     css_spot = pd.concat([power_spot, gas_spot,coal_spot, eua_spot], axis=1, join='inner')
#     css_spot = css_spot.resample('D').mean()
#     css_spot['ghr_spot'] = css_spot['de']/(css_spot['ttf_da']+css_spot['eua']*0.2)
#     css_spot['css_spot'] = css_spot['de']-(css_spot['ttf_da']+css_spot['eua']*0.2)
#     css_spot['cds_spot'] = css_spot['de']/(css_spot['spot_coal']+css_spot['eua']*0.35)
#     css_spot['mc_spot'] = (css_spot['ttf_da']+css_spot['eua']*0.2)/(css_spot['spot_coal']+css_spot['eua']*0.35)
    
#     df = pd.concat([css_spot, de_gen],axis=1,join='inner')
#     df = pd.concat([df, ghr],axis=1, join='inner')
#     df = pd.concat([df, css],axis=1, join='inner')
#     df = pd.concat([df, fr_gen],axis=1, join='inner')
#     df = pd.concat([df, mc_ratio],axis=1, join='inner')

#     sns.regplot(data=df,x='mc_spot', y='cds_spot', order=1)
    
#     df[['DEBYF5_mc', 'DEBYF5']].plot()
       
    
    
    
    
    
    
    

        
        

