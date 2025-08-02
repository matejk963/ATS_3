# -*- coding: utf-8 -*-
"""
Created on Sun Jan 14 10:42:29 2024

@author: krajcovic
"""
import abc

import pandas as pd
import numpy as np
from scipy.stats import kurtosis
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time
from dateutil.relativedelta import relativedelta
import datetime as dt
import seaborn as sns
import os
from sqlalchemy import create_engine, text
from itertools import product

from Loaders.DataLoader_class import DataLoader as DL
from Database.DB_reader import Database  as DB
from Loaders.EikonFut_class import EikonFut as EF
from Loaders.RLD_fetch import RLDDatabaseData


from scipy.stats import boxcox
from scipy.special import inv_boxcox
from scipy.stats import johnsonsu
from scipy.stats import gaussian_kde

import scipy.stats as stats
from scipy.stats import t, multivariate_t, skew
from statsmodels.distributions.empirical_distribution import ECDF
import itertools


"""
    Monitoring, computing, visulizing various types of price and fundamentals data
    Base class (MonitorClass) accepts parameters in params_dict that applies for all
desired data
    
    params_dict {'market_list': [list of markets/grids],
                 'product_list': [list of products either relative: M_1 => front month(only current or continous
                                                                     based on 'cont' condition)/
                                                or absolute:  M.1 => January],
                 'delivery_list': [list of delivery of products: 'base'/'peak'],
                 'year_list': [list of years of the products/ None for relative products],
                 'sD': datetime(y,m,d) of start of the series,
                 'eD': datetime(y,m,d) of end of series,
                 'cont': bool for fething the continouse contracts}
"""

class MonitorClass:
    __metaclass__ = abc.ABCMeta
    
    def __init__(self, params_dict):
       
        self._ef_inst = []

        self._params_dict = params_dict
        self._grid_list = None
        
    
    
    @property
    def params_dict(self):
        return self._params_dict
    
    def update_params(self, new_params_dict):
        self._params_dict = new_params_dict
    
    @property
    def market_list(self):
        return self.params_dict['market_list']
    
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
    def grid_list(self):
        if self._grid_list is None:
            return list(self.market_list)
        else:
            return self._grid_list
    
    @property
    def ef_inst(self):
        if self._ef_inst is None:
            self._ef_inst = [EF(market=market) for market in self.market_list]
        
    
    def get_data(self, reference_date=pd.to_datetime(dt.date.today())):
        return EF(params_dict=self.params_dict, 
                  cont=self.cont).fwd_df(self.sD, self.eD)
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
                                    
    def get_power_spot(self, grid_list):
        
        db_reader = DB()
        df_spot = db_reader.getSpotPriceData(listOfMarkets=grid_list,
                                             _from=self.sD.strftime('%Y-%m-%d'),
                                             _to=self.eD.strftime('%Y-%m-%d'))
        return df_spot
    
    
    
    def get_gas_spot(self):
        ef_inst = EF({})
        out_df = ef_inst.gas_da_df(self.sD, self.eD)
        out_df = self.fill_weekends(out_df)
        out_df.index.name = 'date'
        return out_df
    
    @staticmethod
    def fill_weekends(out_df):
        # Generate a full date range from the start to the end of the provided data
        full_date_range = pd.date_range(start=out_df.index.min(),
                                        end=out_df.index.max())
        
        # Reindex the DataFrame to include all dates in the range, filling missing values
        out_df = out_df.reindex(full_date_range).ffill()
        return out_df
    
    def get_eua_df(self):       
        
        params_dict = {}
        params_dict['market_list'] = ['eua']
        params_dict['product_list'] = ['Y_1']
        params_dict['year_list'] = [None]
        params_dict['delivery_list'] = ['base']
        
        ef_inst = EF(params_dict=params_dict,
                     cont=True)
        
        df = ef_inst.fwd_df(self.sD, self.eD)
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
        params_dict = {}
        params_dict['market_list'] = ['coal'] *2
        params_dict['product_list'] = ['M_0', 'M_1']
        params_dict['year_list'] = [None] * len( params_dict['product_list'])
        params_dict['delivery_list'] = ['base'] * len( params_dict['product_list'])

        ef_inst = EF(params_dict=params_dict,
                     cont=True)
        coal_df = ef_inst.fwd_df(self.sD, self.eD, data_to_keep=['settle', 'all'])
        bom, front_month = coal_df.columns
        coal_df['spot_coal'] = estimate_spot_price(coal_df, bom, front_month)
        coal_spot = self.fill_weekends(coal_df[['spot_coal']].\
                                       reindex(pd.date_range(self.params_dict['sD'],
                                                             self.params_dict['eD'])).copy())
        coal_spot.index.name = 'date'
        return coal_spot
    
    
    # This is utility method for all classes that will generate no. of hours
    # in the period for base or peak
    @staticmethod
    def get_contract_hours(periods, years, b_p='base'):
        def is_weekday(date):
            # 0 is Monday, 6 is Sunday
            return date.weekday() < 5
        
        hours_list = []

        for period, year in zip(periods, years):
            # Determine the start and end dates of each period
            if 'M' in period:
                _, month = period.split('.')
                month = int(month)
                start_date = datetime(year, month, 1)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            elif 'Q' in period:
                _, quarter = period.split('.')
                quarter = int(quarter)
                start_month = (quarter - 1) * 3 + 1
                start_date = datetime(year, start_month, 1)
                if start_month == 10:
                    end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = datetime(year, start_month + 3, 1) - timedelta(days=1)
            
            # Calculate hours based on the b_p value
            total_hours = 0
            current_date = start_date
            while current_date <= end_date:
                if b_p == 'base':
                    total_hours += 24
                elif b_p == 'peak' and is_weekday(current_date):
                    total_hours += 11  # From 9 to 20, inclusive
                    
                current_date += timedelta(days=1)
            
            hours_list.append(total_hours)
        
        return hours_list
    
      

         
            
class FuturesMonitor(MonitorClass):
    """
    For creation of futures prices before and during settlement
    Using above calculation for creating spreads either of the same maturity
    or calendar (taking into consideration the different the different maturities)
    """
    def __init__(self, params_dict):
        super().__init__(params_dict)
        self._ef_inst = EF(params_dict)
        self._leg_list = []
        
    @property
    def ef_inst(self):
        return self._ef_inst
    
    @property
    def leg_list(self):
        return self._leg_list
        
     
    # Define legs creating function
    # This should take data from params_dict and for each create series
    # that goes until the last settlement day of the contract
    def calculate_dates(self):
        start_dates = []
        end_dates = []
        
        for period, year in zip(self.product_list, self.year_list):
            if '.' in period:
                start_date, end_date = self._calculate_absolute_period(period, year)
            else:
                start_date, end_date = self._calculate_relative_period(period)
            
            start_dates.append(start_date)
            end_dates.append(end_date)
        
        return start_dates, end_dates

    def _calculate_absolute_period(self, period, year):
        period_type, period_number = period.split('.')
        period_number = int(period_number)

        if period_type == 'M':
            start_date = datetime(year, period_number, 1)
            end_date = start_date + relativedelta(months=1, days=-1)
        elif period_type == 'Q':
            start_month = (period_number - 1) * 3 + 1
            start_date = datetime(year, start_month, 1)
            end_date = start_date + relativedelta(months=3, days=-1)
        elif period_type == 'Y':
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)
        
        return start_date, end_date

    def _calculate_relative_period(self, period):
        today = datetime.today()
        period_type, period_number = period.split('_')
        period_number = int(period_number)

        if period_type == 'M':
            start_date = today + relativedelta(months=period_number)
            start_date = start_date.replace(day=1)
            end_date = start_date + relativedelta(months=1, days=-1)
        elif period_type == 'Q':
            # Calculate the current quarter
            current_quarter = (today.month - 1) // 3 + 1
            # Calculate the target quarter by adding period_number to the current quarter
            target_quarter = current_quarter + period_number
            # Adjust for year changes
            target_year = today.year + (target_quarter - 1) // 4
            target_quarter = (target_quarter - 1) % 4 + 1  # Ensure quarter is within 1-4
            # Calculate the start month of the target quarter
            start_month = (target_quarter - 1) * 3 + 1
            # Set the start date to the first day of the target quarter's start month
            start_date = datetime(target_year, start_month, 1)
            # Set the end date to the last day of the target quarter
            end_date = start_date + relativedelta(months=3, days=-1)
        elif period_type == 'Y':
            start_date = today + relativedelta(years=period_number)
            start_date = start_date.replace(month=1, day=1)
            end_date = start_date.replace(month=12, day=31)

        return start_date, end_date
    
    # This method is left for now just to process absolute reference
    # Commented part is to be repaired
    @staticmethod
    def quarter_to_months(period, year):
        months_list = []
        years_list = []
    
        # Determine the quarter and whether it's absolute or relative
        if '.' in period:  # Absolute quarter
            _, quarter = period.split('.')
            quarter = int(quarter)
            start_month = (quarter - 1) * 3 + 1
            
            for month_offset in range(3):
                months_list.append(f'M.{start_month + month_offset}')
                years_list.append(year)
    
        # elif '_' in period:  # Relative quarter
        #     _, quarter = period.split('_')
        #     quarter = int(quarter)
        #     today = datetime.today()
        #     start_date = today + relativedelta(months=(quarter-1)*3)  # Adjust to the beginning of the relative quarter
            
        #     for month_offset in range(3):
        #         future_date = start_date + relativedelta(months=month_offset)
        #         months_ahead = (future_date.year - today.year) * 12 + future_date.month - today.month
        #         months_list.append(f'M_{months_ahead}')
        #         years_list.append(None)
    
        return months_list, years_list
    
    @staticmethod
    def cascade_year(last_date):
        year = last_date.year
        month = last_date.month
        
        # Determine the current quarter and the last month of that quarter
        current_quarter = (month - 1) // 3 + 1
        last_month_of_current_quarter = current_quarter * 3
        
        # Generate months leading up to and including the last_date month
        months = [f'M.{m}' for m in range(1, month + 1)]
        years = [year for _ in range(1, month + 1)]
        
        # If not in the last month of the current quarter, add remaining months of the current quarter
        if month < last_month_of_current_quarter:
            for m in range(month + 1, last_month_of_current_quarter + 1):
                months.append(f'M.{m}')
                years.append(year)
        
        # Determine the next quarter to start from
        next_quarter_start_month = last_month_of_current_quarter + 1
        next_quarter = current_quarter + 1
        
        # For the remaining quarters of the year, add them if applicable
        for q in range(next_quarter, 5):
            if next_quarter_start_month <= 12:  # Ensure we're within the current year
                if q * 3 <= 12:  # Ensure this quarter is within the current year
                    # If in the last month of the quarter, add the next quarter's months instead
                    if month == last_month_of_current_quarter and q == next_quarter:
                        for m in range(next_quarter_start_month, next_quarter_start_month + 3):
                            months.append(f'M.{m}')
                            years.append(year)
                    else:
                        months.append(f'Q.{q}')
                        years.append(year)
            next_quarter_start_month += 3
        
        return months, years
    
    def get_partial_products(self, new_prods, new_years,
                             market, delivery,
                             sD, eD):

        # Get new EikonFut class instance
        new_dict = {}
        new_dict['market_list'] = [market] * len(new_prods)
        new_dict['delivery_list'] = [delivery] * len(new_prods)
        new_dict['product_list'] = new_prods
        new_dict['year_list'] = new_years
        ef_inst = EF(new_dict)
        data = ef_inst.fwd_df(sD, eD)
        data = data.fillna(method='ffill')
        # Get weights that corresponds to the no. of hours within each
        # partial product
        weights = self.get_contract_hours(new_prods, new_years)
        assert len(weights) == len(data.columns)
        averaged_data = data.mul(weights).sum(axis=1)/sum(weights)
        
        return averaged_data
        
        
    # Update the spread df by series from legs to get values
    # that are in settlement
    def update_df_by_liq_data(self, df):
        for col, leg in zip(df.columns, self.leg_list):
            df[col] = df[col].combine_first(leg)
            
        return df
    
    # Separate function for getting dates of legs for purpose
    # of knowing which leg to settle with partial closing (leg not in delivery)
    def update_and_extract_df(self, df):
        self.start_dates, self.end_dates = self.calculate_dates()
        delimiters = self.ef_inst.get_delimiter()
        
        spread_start_date = min(self.start_dates)
        spread_end_date = min(self.end_dates)
        
        df = df[:spread_end_date].copy()
        self.df_last_date = df.index[-1]
        return delimiters, spread_start_date, spread_end_date, df
        
    
    def create_legs(self):
        assert len(self.market_list) == 2, 'Too many elemnts for spread'
        
        df = self.get_data()
        
        delimiters, spread_start_date,\
            spread_end_date, df = self.update_and_extract_df(df)
        
        # start_dates, end_dates = self.calculate_dates()
        # delimiters = self.ef_inst.get_delimiter()
        
        # spread_start_date = min(start_dates)
        # spread_end_date = min(end_dates)
        
        # df = df[:spread_end_date].copy()
        # df_last_date = df.index[-1]
        
        leg_list = []
        for leg, market, prod, delivery, year, delimiter in zip(df.columns,
                                    self.market_list,
                                   self.product_list,
                                   self.delivery_list,
                                   self.year_list,
                                   delimiters):
            aux = df[leg].dropna().copy()
            if self.df_last_date<spread_start_date:
                self.leg_list.append(aux)
            elif spread_end_date >= self.df_last_date >= spread_start_date:
                if prod.split(delimiter)[0] in ['Q']:
                    new_prods, new_years = self.quarter_to_months(prod, year)
                    leg = self.get_partial_products(new_prods, new_years,
                                                          market, delivery,
                                                          spread_start_date,
                                                          spread_end_date)
                    leg.name = market + '_' + prod
                    self.leg_list.append(leg)
                elif prod.split(delimiter)[0] in ['Y']:
                    new_prods, new_years = self.cascade_year(self.df_last_date)
                    leg = self.get_partial_products(new_prods, new_years,
                                                          market, delivery,
                                                          spread_start_date,
                                                          spread_end_date)
                    leg.name = market + '_' + prod
                    self.leg_list.append(leg)
                else:
                    self.leg_list.append(aux)
        df = self.update_df_by_liq_data(df)
        leg1_col, leg2_col = df.columns
        self.leg1 = df[leg1_col].copy()
        self.leg2 = df[leg2_col].copy()
        
        
    def settle_non_del_leg(self):
        def weighted_avg_series(leg, first_date, last_date, b_p='base'):
            # Initialize an empty Series to store the weighted average for each date
            weighted_avgs = pd.Series(index=leg[first_date:last_date].index, dtype=float)
        
            # Total number of days in the date range
            total_days = (last_date - first_date).days + 1
        
            # Directly copy the first value in 'leg' to the weighted averages
            if not leg.empty:
                weighted_avgs.iloc[0] = leg[first_date:last_date].iloc[0]
            
            # Start computation from the second value in 'leg'
            for date in leg[first_date:last_date].index[1:]:  # Skip the first date
                # Cumulative days up to but not including the current date
                cum_days = (date - first_date).days
                
                # Calculate cumulative average for days before the current date
                cum_avg = leg[first_date:date - pd.Timedelta(days=1)].mean()
                
                # Weight for the cumulative average
                weight_cum_avg = cum_days / total_days
                
                # Weight for the value on the current date
                weight_current_value = (total_days - cum_days) / total_days
                
                # Calculate weighted average for the current date
                current_value = leg[date]
                weighted_avg = (cum_avg * weight_cum_avg) + (current_value * weight_current_value)
                
                # Store the weighted average
                weighted_avgs[date] = weighted_avg
        
            return weighted_avgs
            
        first_settle_date = min(self.start_dates)
        fsd_index = self.start_dates.index(first_settle_date)
        if self.start_dates[0] != self.start_dates[1]:
            if self.start_dates[fsd_index]<self.df_last_date:
                if fsd_index == 1:
                    self.leg1 = weighted_avg_series(self.leg1,
                                                    self.start_dates[fsd_index],
                                                    self.end_dates[fsd_index])
                elif fsd_index == 0:
                    self.leg2 = weighted_avg_series(self.leg2,
                                                    self.start_dates[fsd_index],
                                                    self.end_dates[fsd_index])
        
        
                    
        
        
    def create_spread_name(self):
        # Extract lists from the dictionary
        market_list = self.params_dict['market_list']
        product_list = self.params_dict['product_list']
        year_list = self.params_dict['year_list']
        
        # Initialize the name parts
        parts = []
        
        # Add the first market, product, and year
        parts.append(f"{market_list[0].upper()}_{product_list[0]}")
        
        # Check if the second year is the same as the first
        if year_list[0] != year_list[1]:
            parts.append(str(year_list[0]))
        
        # Check if the second market is the same as the first
        if market_list[0] != market_list[1]:
            parts.append(market_list[1].upper())
        
        # Add the second product
        parts.append(product_list[1])
        
        parts.append(str(year_list[1]))
        
        # Combine all parts
        name = '_'.join(parts)
        
        return name
        
    
    # Define spreading function
    # This function should take only 2 legs
    def spread_maker(self, diff='abs'):
        self.create_legs()
        # Asser leg1 and leg2 exists
        assert self.leg1 is not None, "Leg1 is missing"
        assert self.leg2 is not None, "Leg2 is missing"
        
        
        spread = pd.concat([self.leg1, self.leg2], axis=1, join='inner')
        col1, col2 = spread.columns
        spread_name = self.create_spread_name()
        if diff in ['abs']:
            spread[spread_name] = spread[col1]-spread[col2]
        else:
            spread[spread_name] = spread[col1]/spread[col2]
            
            
    # def
            
        
        
        return spread
    
class SettleMonitor(MonitorClass):
    
    """
    Class for monitoring settlement prices of power and power fuels
    Default gas is TTF
    Default coal is API2
    """
    def __init__(self, params_dict):
        super().__init__(params_dict)
        
        
    def get_spot_data_raw(self):
        spot_df = pd.DataFrame()
        data_dict = {}
        for market, delivery in zip(self.params_dict['market_list'],
                                    self.params_dict['delivery_list']):
            if market in ['gas']:
                aux = self.get_gas_spot().resample('h').ffill()
            elif market in ['coal']:
                aux = self.get_coal_spot().resample('h').ffill()
            elif market in ['eua']:
                aux = self.get_eua_df().resample('h').ffill()
            else:
                aux = self.get_power_spot([market])
            if spot_df.empty:
                spot_df = aux.copy()
            else:
                if not aux.columns[0] in spot_df.columns:
                    try:
                        aux = aux[~aux.index.duplicated(keep='last')].copy()
                        spot_df = pd.concat([spot_df, aux], axis=1, join='outer')
                    except:
                        print('660')
            
                
        return spot_df
    
    @staticmethod
    def get_peak_mask(df):
        return (df.index.hour >= 9) & (df.index.hour <= 20) & (df.index.weekday < 5)
    
    
    def aggregate_by_time(self, df, tenor, delivery, period=None, dist=False):
        # Apply delivery-based filtering if necessary
        if delivery in ['peak']:
            df = df[self.get_peak_mask].copy()
            
        # Resample and aggregate based on tenor
        if tenor in ['m', 'M']:
            df_m = df.resample('ME').mean()
        elif tenor in ['q', 'Q']:
            df_m = df.resample('QE').mean()
        elif tenor in ['y', 'Y']:
            df_m = df.resample('YE').mean()
    
        # Filter based on the period parameter
        if period is not None:
            if tenor in ['m', 'M']:  # Monthly filtering
                df_m = df_m[df_m.index.month == period]
            elif tenor in ['q', 'Q']:  # Quarterly filtering
                if period == 1:
                    df_m = df_m[df_m.index.month.isin([1, 2, 3])]
                elif period == 2:
                    df_m = df_m[df_m.index.month.isin([4, 5, 6])]
                elif period == 3:
                    df_m = df_m[df_m.index.month.isin([7, 8, 9])]
                elif period == 4:
                    df_m = df_m[df_m.index.month.isin([10, 11, 12])]
        
    
        # Return distribution if requested
        if dist:
            return df_m, df
        else:
            return df_m
        
    def get_final_settlement(self, dist=False):
        df = self.get_spot_data_raw()
        final_df = pd.DataFrame()
        for col, prod, delivery in zip(df.columns,
                                       self.params_dict['product_list'],
                                       self.params_dict['delivery_list']):
            aux = df[col].copy()
            tenor, period = prod.split('.')
            final_aux = self.aggregate_by_time(aux, tenor,
                                               delivery, int(period),
                                               dist)
            if final_df.empty:
                final_df = final_aux.copy()
            else:
                final_df = pd.concat([final_df, final_aux],axis=1,join='outer')
                
        return final_df
    
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
    
    
class FuelSpreadsMonitor(MonitorClass):
    
    def __init__(self, params_dict):
        super().__init__(params_dict)      
        
        
    
        
    
    
    def get_fs_data(self):
        self.power = self.get_data()
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
            self.get_fs_data()
        css = self.power - 2*(self.gas+self.eua*0.2)
        css.columns = [a + '_css' for a in css.columns]
        # css.index
        ghr = self.power / (self.gas + self.eua*0.2)
        ghr.columns = [a + '_ghr' for a in ghr.columns]
        return css, ghr
    
    def get_cds(self):
        if not hasattr(self, 'power'):
            self.get_fs_data()
        cds = self.power - (self.coal/6.15 + self.eua*0.35)/0.35
        cds.columns = [a + '_cds' for a in cds.columns]
        _chr = self.power / (self.coal/6.15 + self.eua*0.35)
        _chr.columns = [a + '_chr' for a in _chr.columns]
        return cds, _chr
    
    def get_mc_ratio(self):
        if not hasattr(self, 'power'):
            self.get_fs_data()
        mc_ratio = (self.gas + self.eua*0.2)/(self.coal/6.15 + self.eua*0.35)
        mc_ratio.columns = [a + '_mc' for a in mc_ratio.columns]
        return mc_ratio




class AvCapMonitor:
    def __init__(self, country='de',
                 config=r"Z:\EnergyTrading\configDB.json"):
        self._country = country
        self._sD = None
        self._eD = None
        self._db_inst = RLDDatabaseData(config)
        self._config = config
        self._rm_inst = None
        
    @property
    def db_inst(self):
        return self._db_inst
    
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
    def rm_inst(self):
        if self._rm_inst is None:
            self._rm_inst = RldMonitor()
            self._rm_inst.set_date_range(self.sD, self.eD)
        return self._rm_inst
    
    @property
    def country_dict(self):
        my_dict = {}
        my_dict['de'] = 'DEU'
        my_dict['fr'] = 'FRA'
        my_dict['it'] = 'ITA'
        my_dict['nl'] = 'NLD'
        my_dict['be'] = 'BEL'
        my_dict['at'] = 'AUT'
        
        return my_dict
    
    @property
    def av_cap_type(self):
        map_dict = {
                'AvCap': 'FUND_AvailCap',
                'InstCap': 'FUND_InstCap'
                }
        return map_dict
        
            
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
        
    def get_data_da(self,market='de', fund_type='AvCap', source='local'):

        if source in ['db']:
            
            country = self.country_dict[market]
            schema_name = self.av_cap_type[fund_type]
            table_name = country + '_12'
            
            df = self.rm_inst.get_fund_data_db(schema_name,
                                                table_name)
            # Normalize to dates by stripping time part
            df['value_date_normalized'] = df['value_date'].dt.normalize()
            df['forecast_date_normalized'] = df['forecast_date'].dt.normalize()
            
            # Filter rows where forecast date is the full day (midnight to midnight) after the value date
            av_cap = df[(df['forecast_date_normalized'] + pd.DateOffset(days=1))
                        == df['value_date_normalized']].copy()
            
            av_cap = av_cap.drop(['forecast_date_normalized',
                                  'value_date_normalized'], axis=1)
            av_cap = av_cap.sort_values(['value_date', 'forecast_date'])
            av_cap = av_cap.ffill()
            av_cap.set_index('value_date', inplace=True)
            av_cap = av_cap.loc[~av_cap.index.duplicated(keep='last')]
            av_cap = av_cap.resample('min').ffill()
            
            av_cap = av_cap.resample('h').mean()
            av_cap.drop(['forecast_date'],axis=1,inplace=True)
                
            
            return av_cap
        if source in ['local']:
            folder_path = r'C:\Users\krajcovic\Documents\Trading\Data\FundDatabase\AvCap'
            market_folder = self.country_dict[market]
            av_cap = pd.DataFrame()
            for date in pd.date_range(self.sD,self.eD):
                file_name = market.upper() + '_av_cap_' + date.strftime('%Y%m%d') + '.csv'
                file_path = os.path.join(folder_path, market_folder, file_name)
                aux = pd.read_csv(file_path, parse_dates=['datetime', 'date', 'f_date'],
                                  dtype=float, index_col='datetime').drop(['date', 'f_date'],axis=1)
                aux = aux.loc[date+dt.timedelta(hours=24):date+dt.timedelta(hours=47)].copy()
                if av_cap.empty:
                    av_cap = aux.copy()
                else:
                    av_cap = pd.concat([av_cap, aux])
            av_cap.columns = [a+'_'+market for a in av_cap.columns]
            return av_cap
        
    def get_data_fcst(self, market, forecast_date,
                      sD, eD,
                      fund_type='AvCap',
                      source='local'):
        if source in ['db']:
            
            country = self.country_dict[market]
            schema_name = self.av_cap_type[fund_type]
            table_name = country + '_12'
            
            df = self.rm_inst.get_fund_data_db(schema_name,
                                                table_name)
            # Normalize to dates by stripping time part
            df['forecast_date_normalized'] = df['forecast_date'].dt.normalize()
            
            # Filter rows where forecast date is the full day (midnight to midnight) after the value date
            av_cap = df.loc[pd.to_datetime(df['forecast_date_normalized'].dt.date)
                            ==forecast_date].copy()
            av_cap = av_cap.drop(['forecast_date_normalized'], axis=1)
            av_cap.set_index('value_date', inplace=True)
            av_cap = av_cap.resample('min').ffill().resample('h').mean()
            av_cap.reset_index(inplace=True)
            av_cap = av_cap.loc[((av_cap['value_date']>=sD)&
                                 (av_cap['value_date']<(pd.to_datetime(eD.date())
                                                        +dt.timedelta(days=1))))].copy()    
            av_cap.drop(['forecast_date'],axis=1,inplace=True)
            av_cap.set_index('value_date',inplace=True)
            
            
            
            return av_cap
        if source in ['local']:
            folder_path = r'C:\Users\krajcovic\Documents\Trading\Data\FundDatabase\AvCap'
            market_folder = self.country_dict[market]
            file_name = market.upper() + '_av_cap_' + forecast_date.strftime('%Y%m%d') + '.csv'
            file_path = os.path.join(folder_path, market_folder, file_name)
            aux = pd.read_csv(file_path, parse_dates=['datetime', 'date', 'f_date'],
                              dtype=float, index_col='datetime').drop(['date', 'f_date'],axis=1)
            aux = aux.loc[sD:eD].copy()
            return aux
        
    def get_data_fcst_raw(self, market, fund_type='AvCap', source='db'):
        if source in ['db']:
            
            country = self.country_dict[market]
            schema_name = self.av_cap_type[fund_type]
            table_name = country + '_12'
            
            df = self.rm_inst.get_fund_data_db(schema_name,
                                                table_name)
            
            # Normalize to dates by stripping time part
            df['forecast_date_normalized'] = df['forecast_date'].dt.normalize()
            
            # Filter rows where forecast date is the full day (midnight to midnight) after the value date
            av_cap = df.loc[((pd.to_datetime(df['forecast_date_normalized'].dt.date)
                            >=self.sD)&
                             (pd.to_datetime(df['forecast_date_normalized'].dt.date)
                                             <=(self.eD+dt.timedelta(days=1))))].copy()
            av_cap = av_cap.drop(['forecast_date_normalized'], axis=1)
            return av_cap
            
       
            




class RldMonitor:
    
    def __init__(self, country='de',
                 config=r"Z:\EnergyTrading\configDB.json"):
        self._country = country
        self._sD = None
        self._eD = None
        self._db_inst = RLDDatabaseData(config)
        self._config = config
        self.df_months = None
        self.df_weekday = None
        self.df_hour = None
        self.value_quantiles = None
        self.hist_quantiles = None
        self.forward_days = None
        
        # self.mask_dict = {'month': None,
        #                   'weekday': None,
        #                   'hour': None,
        #                   'value_position': None,
        #                   'hist_position': None,
        #                   'days_forward': None}
        
        self.mask_dict = {}       
        self.data_dict = {}
        
        # self._dataload_inst = None
        if self._config:
            self._db_inst = DB(path_name=self._config)
        else:
            self._db_inst = DB()
        
        
        
    @property
    def db_inst(self):
        return self._db_inst
    
    
    @property
    def dataloader_inst(self):
        if hasattr(self, '_dataloader_inst'):
            return self._dataloader_inst
        else:
            self._dataloader_inst = DL(self.sD, self.eD, {}, {}, self._config)
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
    
    @property
    def country_dict(self):
        my_dict = {}
        my_dict['de'] = 'DEU'
        my_dict['fr'] = 'FRA'
        my_dict['it'] = 'ITA'
        my_dict['nl'] = 'NLD'
        my_dict['be'] = 'BEL'
        my_dict['at'] = 'AUT'
        my_dict['hu'] = 'HUN'
        my_dict['ro'] = 'ROU'
        my_dict['cz'] = 'CZE'
        my_dict['sk'] = 'SVK'
        my_dict['osc'] = 'OSC'
        
        return my_dict
        
            
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
    def adjust_normal(self,normal,market,source,
                      long, monthly, monthly_parts,
                      consumption_only=True):
        monthly = self.get_raw_data(market=market,
                                        source=source,
                                        long=long, monthly=monthly,
                                        monthly_parts=monthly_parts)
        if consumption_only:
            fund='CON'
            aux = monthly[['forecast_date', 'value_date',fund]].copy()
            aux = aux.rename(columns={fund: 'rld'})
            aux_process = self.process_data(aux)
            aux_process = aux_process.rename(columns={'rld' : fund})
            aux_da = self.get_da_data(aux_process).set_index('value_date')
            aux_da = aux_da.rename(columns={0: fund})
            return aux_da
        else:
            raise ValueError('Need to define other fundamentals to adjust normal for')
            
    def get_fund_data_db(self, schema_name, table_name, ec_type=0,
                         sD_fcst=None, eD_fcst=None):
        """
        Raw residual forecast data fetch
            Method to fetch FORECASTED data for Residual demand calculation (Consumption, Wind, Solar) where
        the output is dataframe where for each value from date_range(sD_fcst-eD_fcst) the full
        EC forecast is fetched from database.
            Resulting shape is thus (n*fcst_lenght, m) where
        n = no. of forecast dates in date_range(sD_fcst-eD_fcst)
        fcst_lenght = no. of hours the forecast (EC_ens00) provide
        m = columns ['forecast_date', 'value_date', 'con', 'wind', 'solar']

        ec_type : int, specifies the type of EC forecast (0,6,12,18)/default=0
        country : str, specifies the country to fetch the data for/default='de'
        sD_fcst/eD_fcst : datetime.datetime, default values are assigned with __init__
        """

        db_obj = self._db_inst
        con = db_obj.connection_string
        engine = create_engine(con)


        if sD_fcst is None:
            sD_fcst = self.sD
        if eD_fcst is None:
            eD_fcst = self.eD

        # Ensure sD_fcst and eD_fcst are not None and are properly formatted dates (as strings)
        if sD_fcst is None or eD_fcst is None:
            raise ValueError("Start date and end date must be provided.")
            
        # Date range: modify these dates to your requirements
        start_date = sD_fcst  # Start date
        end_date = eD_fcst + dt.timedelta(seconds=24*60*60-1)  # End date
        
        # Example table and schema names
        # schema_name = "FUND_ResidualDemand"
        # table_name = "DEU_00"
        
        # Prepare the query using placeholders without injecting variables directly
        # Note the use of double quotes to preserve the exact case of identifiers
        if 'normal' in [a.lower() for a in ['normal', 'ntc', 'syn']] and 'normal' in schema_name.lower():
            # Query for 'normal' case: select from start_date to the last available date (no end_date condition)
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE value_date >= :start_date;
            """)
        elif any(a.lower() in schema_name.lower() for a in ['ntc', 'syn']):
            # Query for 'ntc' and 'syn' cases: select between start_date and end_date
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE forecast_date BETWEEN :start_date AND :end_date;
            """)
        else:
            # Fallback or other cases can be handled here if necessary
            query = text(f"""
            SELECT * FROM "{schema_name}"."{table_name}"
            WHERE forecast_date BETWEEN :start_date AND :end_date;
            """)

        
        # Use pandas to read the SQL query into a DataFrame
        df = pd.read_sql(query, engine, params={'start_date': start_date, 'end_date': end_date})

        return df
    
    
    def get_raw_data(self, fcst_type, fund,
                     ec_type,
                     market='de', source='db'):
        country = self.country_dict[market]
        if source in ['db']:
            schema_name = 'FUND_' + fund + '_' + fcst_type
            schema_name = schema_name.replace('_mid','')
            if not fcst_type in ['normal']:
                table_name = country + '_' + (ec_type)
            else:
                table_name = country
            # table_name = table_name.replace('_ ', '')
            df = self.get_fund_data_db(schema_name, table_name)
            return df
        elif source in ['local']:
            if fcst_type in ['normal']:
                file_name = country + '_' + fund + '_norm.csv'
                folder_path = r'Z:\Data\Normals\Normals'
                file_path = os.path.join(folder_path, file_name)
                df = pd.read_csv(file_path,
                                     parse_dates=['datetime'])
                df.columns = ['value_date', fund]
                df = df.loc[~df['value_date'].duplicated()].copy()
                return df
                
            
        
    def get_fund_data(self,fcst_type, fund_type, 
                          ec_type, market='de', source='db'):
        if fcst_type in ['mid']:
            if fund_type in ['res']:
                if not  market in ['de', 'hu', 'ro']:
                    aux_rld = self.get_raw_data(fcst_type,'ResidualDemand', ec_type,
                                            market, source)
                    aux_con = self.get_raw_data(fcst_type,'CON', ec_type,
                                            market, source)
                    aux_mid = aux_con.merge(aux_rld, on=['forecast_date', 'value_date'],
                                         how='inner')
                   
                    aux_mid['res'] = aux_mid['CON'] - aux_mid['rld']
                else:
                    aux_wind = self.get_raw_data('mid', 'Wind', ec_type,
                                                 market, source)
                    aux_solar = self.get_raw_data('mid', 'Solar', ec_type,
                                                 market, source)
                    aux_mid = aux_wind.merge(aux_solar, on=['forecast_date', 'value_date'],
                                         how='inner')
                    aux_mid['Wind'] = aux_mid['Wind'].fillna(0)
                    aux_mid['Solar'] = aux_mid['Solar'].fillna(0)
                    
                    aux_mid['res'] = aux_mid['Wind'] + aux_mid['Solar']
                
                                                          
                return aux_mid[['forecast_date', 'value_date', 'res']]
            else:
                if (fund_type in ['ResidualDemand']) and (market.upper() not in ['DE', 'FR', 'NL',
                                                                      'BE', 'AT', 'CZ']):
                    aux_mid = self.get_raw_data(fcst_type,'CON', ec_type,
                                            market, source)
                    if market.upper() not in ['HU', 'SK']:
                        aux_wind = self.get_raw_data('mid', 'Wind', ec_type,
                                                     market, source)
                        aux_mid = aux_mid.merge(aux_wind, on=['forecast_date', 'value_date'],
                                             how='left')
                        aux_mid['Wind'] = aux_mid['Wind'].fillna(0)
                    if market.upper() not in ['SK']:
                        aux_solar = self.get_raw_data('mid', 'Solar', ec_type,
                                                     market, source)
                        aux_mid = aux_mid.merge(aux_solar, on=['forecast_date', 'value_date'],
                                             how='left')
                        aux_mid['Solar'] = aux_mid['Solar'].fillna(0)
                    
                    
                    aux_mid['Wind'] = aux_mid.get('Wind',
                                                  pd.Series(0, index=aux_mid.index)).fillna(0)
                    aux_mid['Solar'] = aux_mid.get('Solar',
                                                   pd.Series(0, index=aux_mid.index)).fillna(0)
                    
                    aux_mid['CON'] = aux_mid['CON'].fillna(0)
                    aux_mid['rld'] = aux_mid['CON'] - aux_mid['Wind'] - aux_mid['Solar']
                    return aux_mid[['forecast_date', 'value_date', 'rld']]
                else:
                    
                    aux = self.get_raw_data(fcst_type, fund_type, ec_type,
                                            market, source)
                        
                    if len(aux)==0:
                        print('1200')
                    
                    return aux
            
        else:
            if fund_type in ['ResidualDemand']:
                df = pd.DataFrame()
                for fund in ['CON', 'Wind', 'Solar']:
                    if fund in ['Wind']:
                        if market.upper() in ['HU', 'SK']:
                            continue
                    elif fund in ['Solar']:
                        if market.upper() in ['SK', 'AT']:
                            continue

                    aux = self.get_raw_data(fcst_type, fund, ec_type,
                                                market, source)
                    if len(aux)==0:
                        print('1218')
                   
                    if df.empty:
                        df = aux.copy()
                    else:
                        if fcst_type in ['mnd']:
                            df = df.merge(aux, on=['forecast_date', 'value_date'],how='outer')
                        else:
                            df = df.merge(aux, on=['value_date'],how='outer')
                            
                df['Wind'] = df.get('Wind',pd.Series(0, index=df.index)).fillna(0)
                df['Solar'] = df.get('Solar',pd.Series(0, index=df.index)).fillna(0)

                df['rld'] = df['CON'] - df['Wind'] - df['Solar']
                date_cols = [col for col in df.columns if 'date' in col]
                sel_cols = date_cols + ['rld']
                return df[sel_cols]
            elif fund_type in ['res']:
                aux_wind = self.get_raw_data(fcst_type, 'Wind', ec_type,
                                        market, source)
                aux_solar = self.get_raw_data(fcst_type, 'Solar', ec_type,
                                        market, source)
                if fcst_type in ['mnd']:
                    aux = aux_wind.merge(aux_solar, on=['forecast_date', 'value_date'],
                                         how='inner')
                    
                else:
                    aux = aux_wind.merge(aux_solar, on=['value_date'],
                                         how='inner')
                aux['Wind'] = aux['Wind'].fillna(0)
                aux['Solar'] = aux['Solar'].fillna(0)
                
                aux['res'] = aux['Wind'] + aux['Solar']
                date_cols = [col for col in aux.columns if 'date' in col]
                sel_cols = date_cols + ['res']
                return aux[sel_cols]
            else:
                df = self.get_raw_data(fcst_type, fund_type, ec_type,
                                            market, source)                                   
                return df
            
    def normalize_fund_data(self,fcst_type, fund_type, 
                          ec_type, normalize_to,
                          market='de', source='db'):
        aux_fund = self.get_fund_data(fcst_type, fund_type, 
                              ec_type, market, source)
        if normalize_to in ['ResidualDemand']:
            aux_norm = self.get_fund_data('normal', normalize_to, 
                                  ec_type, market, 'local')
        elif normalize_to in ['CON']:
            aux_norm = self.get_fund_data('normal', normalize_to, 
                                  ec_type, market, 'local')
        elif normalize_to in ['res']:
            aux_norm = self.get_fund_data('normal', normalize_to, 
                                  ec_type, market, 'local')
        elif normalize_to in ['Temp']:
            aux_norm = self.get_fund_data('normal', normalize_to, 
                                  ec_type, market, 'db')
            
            
        aux = aux_fund.merge(aux_norm, on='value_date', how='left', suffixes=('', '_norm'))
        if fund_type in ['ResidualDemand']:
            fund_col = 'rld'
        else:
            fund_col = fund_type
        aux[fund_col] = aux[[fund_col]].values/aux[[col for col in aux.columns if '_norm' in col]].values
        return aux[['forecast_date', 'value_date', fund_col]]
    
    
    def data_matrix(self, df, fund_type, fct_type=0):
        
        
        out_df = df[df['forecast_date'].dt.hour==fct_type].copy()
        out_df = out_df.loc[((out_df['forecast_date']>=self.sD)&
                             (out_df['forecast_date']<=self.eD))].copy()
        value_col = [col for col in out_df.columns if 'date' not in col]
        out_df['hours'] = ((out_df['value_date'] - out_df['forecast_date']).dt.total_seconds()/3600)+1
        out_df[value_col] = out_df[value_col].fillna(method='ffill')
        if out_df['hours'].max() <400:
            out_df = out_df.loc[((out_df['hours']>24)&
                                 (out_df['hours']<361))].copy()
        else:
            out_df = out_df.loc[((out_df['hours']>24))].copy()
        

        out_df = pd.pivot_table(data=out_df, index=['forecast_date'], columns=['hours'], values=value_col)
        out_df = out_df.ffill(axis=1)
        out_df.columns = out_df.columns.droplevel(0)
        if any(a in fund_type.lower() for a in ['inf']):
            # Filling the missing columns
           all_hours = np.arange(out_df.columns.min(), out_df.columns.max() + 1)
           out_df = out_df.reindex(columns=all_hours, fill_value=np.nan)
           out_df = out_df.fillna(method='ffill', axis=1)
        return out_df
    
    
    def get_fund_curve(self,fund_type, 
                          ec_type, normalize_to=None,
                          market='de', source='db', fut_periods=720):
        if market in ['hu', 'ro', 'cz', 'sk']:
            norm_source = 'db'
        else:
            norm_source = 'local'
        if normalize_to is None:
            aux_short = self.get_fund_data('mid', fund_type,
                                           ec_type, market, source)
            short_matrix = self.data_matrix(aux_short, fund_type)
            
            if not fund_type.lower() in ['inf', 'temp']:
                
                aux_normal = self.get_fund_data('normal', fund_type,
                                                ec_type, market, norm_source)
                if market.upper() not in ['SK', 'CZ', 'HU', 'RO']:
                    aux_month = self.get_fund_data('mnd', fund_type,
                                                   ec_type, market, source)           
                    
                    
                    monthly_matrix = self.data_matrix(aux_month, fund_type)
                    additional_columns = [col for col in monthly_matrix.columns
                                          if col not in short_matrix.columns]
                    df = pd.merge(short_matrix,
                                  monthly_matrix[additional_columns],
                                  left_index=True,
                                  right_index=True,
                                  how='left')
                else:
                    df = short_matrix.copy()
                df = df.ffill()
            else:
                aux_normal = self.get_fund_data('normal', fund_type,
                                                ec_type, market, 'db')
                
                df = short_matrix.copy()
            if fund_type in ['CON', 'ResidualDemand']:
                df = self.add_normal_values_to_matrix(df, aux_normal, fut_periods, adjust=True)
            else:
                df = self.add_normal_values_to_matrix(df, aux_normal, fut_periods, adjust=False)
        else:
            aux_short = self.normalize_fund_data('mid', fund_type,
                                           ec_type, normalize_to,
                                           market, source)
            short_matrix = self.data_matrix(aux_short, fund_type)
            if fund_type.lower() not in ['temp']:
                aux_month = self.normalize_fund_data('mnd', fund_type,
                                               ec_type, normalize_to,
                                               market, source)
                # Process them to matrix
                
                monthly_matrix = self.data_matrix(aux_month, fund_type)
                additional_columns = [col for col in monthly_matrix.columns
                                      if col not in short_matrix.columns]
                df = pd.merge(short_matrix,
                              monthly_matrix[additional_columns],
                              left_index=True,
                              right_index=True,
                              how='left')
                df = df.ffill()
            else:
                df = short_matrix.copy()
                df = df.ffill()
            if normalize_to == fund_type:
                
                if fut_periods > df.shape[1]:
                    extra_hours = fut_periods - df.shape[1]
                    zeros_matrix = np.zeros((df.shape[0],extra_hours))
                    zeros_matrix = 1
                    new_columns = np.arange(df.columns[-1]+1,fut_periods+1)
                    aux = pd.DataFrame(zeros_matrix,index=df.index,columns=new_columns)
                    df = pd.concat([df, aux], axis=1)
                    df = df.fillna(1)
                else:
                    df = df.iloc[:,:int(fut_periods-1)].copy()
                    df = df.fillna(1)
            else:
                aux_normal = self.normalize_fund_data('normal', fund_type,
                                                    ec_type, normalize_to,
                                                    market, 'local')
                df = self.add_normal_values_to_matrix(df, aux_normal, fut_periods)
        return df
                
                
                
    
    
    def compile_data(self,markets=['de', 'fr', 'be', 'nl'],
                     fut_periods=720,
                     source='db'):
        for market in markets:
            if market not in list(self.data_dict):
                self.data_dict[market] = {}
                if 'nominal' not in list(self.data_dict[market]):
                    self.data_dict[market]['nominal'] = self.get_fund_curve(fund_type='res',ec_type='00',
                                                                            normalize_to=None, 
                                                                            market=market, source=source,
                                                                            fut_periods=720)
                if 'normalized' not in list(self.data_dict[market]):
                    self.data_dict[market]['normalized'] = self.get_fund_curve(fund_type='res',ec_type='00',
                                                                            normalize_to='res', 
                                                                            market=market, source=source,
                                                                            fut_periods=720)
                if 'CON' not in list(self.data_dict[market]):
                    self.data_dict[market]['CON'] = self.get_fund_curve(fund_type='CON',ec_type='00',
                                                                            normalize_to=None, 
                                                                            market=market, source=source,
                                                                            fut_periods=720)
                
                if 'normal' not in list(self.data_dict[market]):
                    self.data_dict[market]['normal'] = self.data_dict[market]['nominal']/\
                        self.data_dict[market]['normalized']
                

   
    def adjust_CON(self):
        pass
                    
    
    def add_normal_values_to_matrix(self, df, normal_curve, fut_periods, adjust=False):
        first_col, last_col = df.columns[0], df.columns[-1]
        
        if last_col>=fut_periods:
            df = df.iloc[:,:int(fut_periods)].copy()
        else:
            extra_hours = fut_periods - df.shape[1]
            zeros_matrix = np.zeros((df.shape[0],int(extra_hours)))
            zeros_matrix = np.nan
            new_columns = np.arange(df.columns[-1]+1,fut_periods+1)
            aux = pd.DataFrame(zeros_matrix,index=df.index,columns=new_columns)
            df = pd.concat([df, aux], axis=1)
        
        # Step 1: Create a DataFrame of computed datetimes
        # Use np.tile to repeat the index for each column, and np.add.outer to add hours to these dates
        hours = np.array(df.columns.astype(int)-1)  # Ensure the columns are integer type
        datetimes = pd.to_datetime(np.add.outer(df.index.values, np.timedelta64(1, 'h') * hours))
        
        # Convert this array of datetimes into a DataFrame with the same shape and index/columns as df
        datetime_df = pd.DataFrame(datetimes, index=df.index, columns=df.columns)
        
        # Flatten the datetime_df and convert series to DataFrame for alignment
        datetime_flat = datetime_df.stack().reset_index()
        datetime_flat.columns = ['date', 'hour', 'datetime']
        
        series_df = normal_curve
        series_df.columns = ['datetime', 'value']
        
        # Merge on the computed datetime to match series values
        merged_df = pd.merge(datetime_flat, series_df, on='datetime', how='left')
        
        # Step 2: Reshape merged_df back to the original df shape with values aligned
        result_df = merged_df.pivot(index='date', columns='hour', values='value')
        
        # Step 3: Update the original df with values from result_df where df is NaN
        df = df.where(pd.notna(df), result_df)
        
        return df
    
        
        
        
    """
    Here the goal is to get scenarios of the residual loads
    """
    
    
    def rld_chng_mask(self, df, df_act, mask_type, market,
                      percentile_fix=500, value_quantiles=10,
                      hist_quantiles=3,
                      direct_output=False, differences=False):
        start_time = time.time()
        if market not in list(self.mask_dict):
            self.mask_dict[market] = {}

        
        def compute_quantiles(series, initial_fixed, quantiles, step=30):
            # Initialize the output array
            deciles = np.empty(len(series))
            deciles[:] = np.nan  # Fill with NaNs
            
            # Calculate global deciles for the initial fixed part
            global_deciles = np.quantile(series[:initial_fixed].dropna(), np.linspace(0, 1, quantiles + 1))
            
            # Apply initial fixed deciles based on calculated thresholds
            for i in range(1, len(global_deciles)):
                deciles[:initial_fixed] = np.where(series[:initial_fixed] <= global_deciles[i], i - 1, deciles[:initial_fixed])
            
            # Calculate deciles in chunks after the initial fixed part
            for i in range(initial_fixed, len(series), step):
                # Defining the end of the current segment
                end = min(i + step, len(series))
                
                # Calculate deciles for the current window
                window_deciles = np.quantile(series[:end].dropna(), np.linspace(0, 1, quantiles + 1))
                
                # Apply deciles for the current segment
                for j in range(i, end):
                    # It is necessary to loop through each point in the current segment to assign its decile
                    if not np.isnan(series[j]):  # Skip NaN values in original series
                        deciles[j] = np.searchsorted(window_deciles, series.iloc[j], side='right') - 1
        
            return pd.Series(deciles, index=series.index)
        
        
        def calculate_quantiles_vectorized(series, initial_fix_period, no_of_quantiles):
            # Ensure the series is sorted by index if datetime or similar
            series = series.sort_index()
            
            # Handling completely NaN columns
            if series.isna().all():
                return pd.Series([np.nan] * len(series), index=series.index)
            
            # Calculate quantiles for the initial fixed period
            if initial_fix_period <= len(series):
                initial_quantiles = pd.qcut(series[:initial_fix_period], q=no_of_quantiles, labels=False, duplicates='drop')
            else:
                # If the series is shorter than the initial_fix_period, calculate quantiles for the entire series
                initial_quantiles = pd.qcut(series, q=no_of_quantiles, labels=False, duplicates='drop')
            
            # Ensure initial_quantiles is a Series with the correct index
            initial_quantiles = pd.Series(initial_quantiles, index=series.index[:initial_fix_period])
            
            # For the rest of the series, calculate rolling quantiles if the series is longer than the initial_fix_period
            if len(series) > initial_fix_period:
                # Apply the rolling quantile calculation for the rest of the series
                rolling_quantiles = pd.qcut(series[initial_fix_period:], q=no_of_quantiles, labels=False, duplicates='drop')
                
                # Combine initial quantiles with rolling quantiles
                combined_series = pd.concat([initial_quantiles, rolling_quantiles], ignore_index=False)
            else:
                combined_series = initial_quantiles
            
            return combined_series
        
        
        if mask_type in ['month', 'weekday', 'hour']:
            df.index = pd.to_datetime(df.index)
            # Convert the column names to a numpy array of time deltas (assuming they're already floats or can be converted to float)
            hours_shift = np.array([float(col)-1 for col in df.columns]) * np.timedelta64(1, 'h')            
            # Now, broadcast the addition of these time deltas to the datetime index across all rows
            # The reshaping of df.index is to ensure broadcasting works correctly across the DataFrame
            datetimes = df.index.values.reshape(-1, 1) + hours_shift            
            # Convert the numpy array back to a DataFrame with the same structure as the original
            df_transformed = pd.DataFrame(datetimes, index=df.index, columns=df.columns)
            # Assuming 'df_transformed' is your DataFrame from previous steps
            df_transformed = df_transformed.apply(pd.to_datetime)

            if mask_type in ['month']:
                df_months = df_transformed.apply(lambda x: x.dt.month)
                self.mask_dict[market][mask_type] = df_months

            elif mask_type in ['hour']:
                df_hour = df_transformed.apply(lambda x: x.dt.hour)
                # df_hour = pd.DataFrame(np.where(((df_hour>7)&(df_hour<20)),1,0),
                #                        columns=df_hour.columns,
                #                        index=df_hour.index)
                self.mask_dict[market][mask_type] = df_hour//4
        else:
            if mask_type in ['value_position']:
                
                # Apply the function to your column
                initial_fixed = percentile_fix  # Set this to your fixed initial range (e.g., 200)
                quantiles_arr = [pd.Series([np.nan] * len(df_act) if df_act[a].isna().all()
                                            else calculate_quantiles_vectorized(df_act[a],
                                                                                  percentile_fix,
                                                                                  value_quantiles))
                                  for a in df_act.columns]

                quantiles_df = pd.DataFrame(np.array(quantiles_arr).T,
                                       columns=[a for a in df_act.columns],
                                       index=df_act.index)
                self.mask_dict[market][mask_type] = quantiles_df
                
            elif mask_type in ['hist_position']:
                data_da = self.get_da_data(df_act).set_index('value_date').resample('D').mean()

                data_da['roll_mean'] = data_da['rld_da'].rolling(window=14, min_periods=1).mean()
                data_da['quantiles'] = calculate_quantiles_vectorized(data_da['roll_mean'], percentile_fix, hist_quantiles)
                data_da['quantiles'] = np.where(data_da['quantiles']==hist_quantiles,hist_quantiles-1,data_da['quantiles'])
                _, new_index = data_da.align(df, join='inner')                
                data_da = data_da.reindex(new_index.index)
                df = df.reindex(new_index.index)
                quantiles_arr = [data_da['quantiles'] for a in df.columns]
                quantiles_df= pd.DataFrame(np.array(quantiles_arr).T,
                                       columns=[a for a in df.columns],
                                       index=data_da.index)
                if direct_output:
                    return data_da
                else:
                    self.mask_dict[market][mask_type] = quantiles_df
            
            elif mask_type in ['days_forward']:
                days_forward = [(a-1)//24 for a in df.columns]
                aux_arr = [days_forward for a in range(df.shape[0])]
                forward_days = pd.DataFrame(np.array(aux_arr),
                                       columns=[a for a in df.columns],
                                       index=df.index)
                
                
                self.mask_dict[market][mask_type] = forward_days
                
        end_time = time.time()
        print(f"rld_chng_mask took {end_time - start_time} seconds to execute")
            
    def generate_masks(self, df, df_act, market, types='all'):
        if types in ['all']:
            type_list = ['month', 'hour', 'value_position',
                              'hist_position', 'days_forward']
        else:
            type_list = types
        
        
        for mask_type in type_list:
            if market not in list(self.mask_dict):
                self.mask_dict[market] = {}
            if mask_type not in  list(self.mask_dict[market]):
                self.rld_chng_mask(df, df_act, mask_type, market)
                # self.mask_dict[mask_type] = aux
                
        
        # Alternatively, find the intersection of all indices (only dates present in every DataFrame)
        all_dates_intersection = pd.Index(self.mask_dict[market][next(iter(self.mask_dict[market]))].index)  # Start with the index of the first DataFrame
        for df in self.mask_dict[market].values():
            all_dates_intersection = all_dates_intersection.intersection(df.index)

        # Now, reindex all DataFrames to the combined index
        # Replace 'all_dates_union' with 'all_dates_intersection' if you want the intersection instead
        aligned_mask_dict = {name: df.reindex(all_dates_intersection) for name, df in self.mask_dict[market].items()}
        
        
        return aligned_mask_dict, type_list

    def get_mask(self, filter_values, df, df_act, market, scen_type=None, types='all'):
        
        def get_month_spread(value):
            value_from = value-1
            if value_from == 0:
                value_from = 12
            value_to = value+1
            if value_to == 13:
                value_to = 1
            return value_from, value, value_to
        
        masks, types_list = self.generate_masks(df, df_act, market, types)
        assert len(filter_values) == len(types_list)
        keys = types_list
        values = filter_values
        # Check if keys list and values list have the same length to avoid errors
        if len(keys) != len(values):
            raise ValueError("Keys and values lists must have the same length")

        # Types should allways stars with month is you have error pointing here
        # Switch the type_list to start with month        
        # Initialize the result with the comparison of the first DataFrame
        # For each month mask includes month before and after
        selected_masks_dict = {}
        # Loop through the remaining keys and values, updating the result
        for key, value in zip(keys, values):
            if key in ['month']:
                value_from ,value_middle, value_to = get_month_spread(values[0])
                selected_masks_dict[key] = ((masks[key]==value_from)|
                                            (masks[key]==value_to)|
                                            (masks[key]==value_middle))
            else:
                selected_masks_dict[key] = masks[key] == value
        final_masks_dict = {}
        # month_value = values[0]
        # days_fwd_value = values[-1]
        
        # for i, key in enumerate(['hour']):   
        #     # Start from the second item
        #     final_masks_dict[i] = (selected_masks_dict[key]&
        #                              selected_masks_dict['month']&
        #                              selected_masks_dict['days_forward']&
        #                              selected_masks_dict['value_position'])
            
        for i, key in enumerate(['hour']):   
            # Start from the second item
            final_masks_dict[i] = (selected_masks_dict[key]&
                                     selected_masks_dict['month']&
                                     selected_masks_dict['days_forward'])
            
        return final_masks_dict
    
    
    def filter_values(self, filter_values, df, df_act, types='all'):
        mask = self.get_mask(filter_values, df, df_act, types)
        return df[mask]
    
    @staticmethod
    def standardize_with_skew_adjustment(column, window):
        
        """
        Standardize a column using an adjusted rolling mean and std dev after
        correcting for skewness.
        """
        def transform_skewness(column):
            """
            Apply Box-Cox transformation to correct skewness.
            Returns the transformed column and the lambda value used for the transformation.
            """
            # Box-Cox transform requires all positive values
            # column += 1  # Uncomment if adding a constant to handle zero or negative values
            transformed, lam = boxcox(column)
            return transformed, lam
        # Correct skewness first
        column_transformed, lam = transform_skewness(column)

        # Then proceed with rolling mean and std dev
        rolling_mean = pd.Series(column_transformed).rolling(window=window, min_periods=1).mean()
        rolling_std = pd.Series(column_transformed).rolling(window=window, min_periods=1).std()

        # Z-score standardization with skew adjustment
        standardized = (column_transformed - rolling_mean) / rolling_std

        # Transform the last value back to nominal (including reversing the Box-Cox transformation)
        last_mean = rolling_mean.iloc[-1]
        last_std = rolling_std.iloc[-1]
        last_standardized = standardized.iloc[-1]
        last_nominal_transformed = standardized * last_std + last_mean
        last_nominal = inv_boxcox(last_nominal_transformed, lam)

        return last_nominal, last_nominal_transformed
    
        
    
    def get_curve_values(self, curve, df_act, curve_da,
                         lookback=1000,
                         value_quantiles=10,
                         hist_quantiles=3):
        """
        

        Parameters
        ----------
        curve : TYPE
            DESCRIPTION.
        df_act : TYPE
            DESCRIPTION.
        curve_da : TYPE
            DESCRIPTION.
        lookback : TYPE, optional
            DESCRIPTION. The default is 1000.

        Returns
        -------
        series
            series with list values containing conditional values to get scenarios for.

        """
        start_time = time.time()
        def find_value_quantile(value, data_series, num_quantiles):
            """
            Determine the quantile number the value belongs to based on historical data.
        
            :param value: The value to classify.
            :param data_series: A pandas Series of historical data.
            :param num_quantiles: The total number of quantiles to divide the data into.
            :return: The quantile number (0-indexed) that the value belongs to.
            """
            # Calculate the quantile thresholds
            quantile_thresholds = np.quantile(data_series.dropna(), np.linspace(0, 1, num_quantiles + 1))
            
            # Determine which quantile the value belongs to
            quantile_number = np.searchsorted(quantile_thresholds, value, side='right') - 1
            
            # Ensure the quantile number is within the range [0, num_quantiles-1]
            quantile_number = max(0, min(quantile_number, num_quantiles - 1))
            
            return quantile_number
        
        curve.index = pd.to_datetime(curve.index)
        hours_shift = np.array([float(col)-1 for col in curve.columns]) * np.timedelta64(1, 'h')
        datetimes = curve.index.values.reshape(-1, 1) + hours_shift 
        curve_transformed = pd.DataFrame(datetimes, index=curve.index, columns=curve.columns)
        curve_transformed = curve_transformed.apply(pd.to_datetime)
        curve_months = curve_transformed.apply(lambda x: x.dt.month)
        curve_weekday = curve_transformed.apply(lambda x: x.dt.weekday)
        curve_weekday = pd.DataFrame(np.where((curve_weekday<5),1,0),
                               columns=curve_weekday.columns,
                               index=curve_weekday.index)
        curve_hour = curve_transformed.apply(lambda x: x.dt.hour)//4
        # curve_hour = pd.DataFrame(np.where(((curve_hour>7)&(curve_hour<20)),1,0),
        #                        columns=curve_hour.columns,
        #                        index=curve_hour.index)
        days_forward = [(a-1)//24 for a in curve.columns]
        forward_days = pd.DataFrame(np.array([days_forward]),
                               columns=[a for a in curve.columns],
                               index=curve.index)
        
        data_da = self.get_da_data(df_act)
        data_da = data_da['rld_da'].rolling(14).mean().iloc[-lookback:].copy()
        conditions = ['month', 'hour', 'value_position',
                          'hist_position', 'days_forward']
        tot_val_ser = []
        for col in curve.columns:
            aux_val = []
            aux_val_names = []
            aux = curve[col].iloc[0]
            for mask_type in conditions:
                if mask_type in ['month']:
                    aux_val.append(curve_months[col].iloc[0])
                    aux_val_names.append(mask_type)
                elif mask_type in ['weekday']:
                    aux_val.append(curve_weekday[col].iloc[0])
                    aux_val_names.append(mask_type)
                elif mask_type in ['hour']:
                    aux_val.append(curve_hour[col].iloc[0])
                    aux_val_names.append(mask_type)
                elif mask_type in ['value_position']:
                    val = aux
                    val_ser = df_act[col].iloc[-lookback:]
                    quantile = find_value_quantile(val, val_ser, value_quantiles)
                    aux_val.append(quantile)
                    aux_val_names.append(mask_type)
                elif mask_type in ['hist_position']:
                    quantile = find_value_quantile(curve_da, data_da, hist_quantiles)
                    aux_val.append(quantile)
                    aux_val_names.append(mask_type)
                elif mask_type in ['days_forward']:
                    aux_val.append(forward_days[col].iloc[-1])
            tot_val_ser.append(aux_val)
            
        tot_val_df = pd.DataFrame(np.array(tot_val_ser).T,
                                  columns=curve.columns,
                                  index=conditions)
        end_time = time.time()
        print(f"get_curve_values took {end_time - start_time} seconds to execute")
        return tot_val_df
                    
    @staticmethod
    def get_hist_changes(scen_type, normalized_matrix, market='de', source='local'):
        # Fetch normalized data fro up to month ahead forecast
        data = normalized_matrix.copy()
        
        date_index = np.array(data.index).reshape(1,-1)
        
        hours_shift = np.array(data.columns).reshape(-1,1)
        
        
        dates_mask = pd.DataFrame(date_index+(hours_shift-1).astype('timedelta64[h]'),
                                  index=data.columns, columns=data.index).T
        
        m1 = dates_mask.iloc[:,:24].copy()
        m2 = dates_mask.iloc[:,24:].copy()
        m2 = m2[m2<m1.max().max()]
        m2 = m2[~np.isnan(m2).any(axis=1)]
        v1 = normalized_matrix.iloc[:,:24].copy()
        
        # Stack the DataFrames to work with 1D arrays
        m1_stacked = m1.stack()
        m2_stacked = m2.stack()
        v1_stacked = v1.stack()

        # Create a mapping from M1 values to their indices in the stacked array
        m1_to_idx = {value: idx for idx, value in m1_stacked.items()}

        # Use the mapping to get corresponding indices for values in M2
        m2_to_v1_idx = m2_stacked.map(m1_to_idx)

        # Handle the case where values in M2 do not have corresponding entries in M1
        if m2_to_v1_idx.isnull().any():
            print("Warning: Some values in M2 do not have corresponding entries in M1")

        # Use these indices to get values from V1
        v2_stacked = m2_to_v1_idx.map(v1_stacked)

        # Unstack the result to get back to the original DataFrame shape
        V2 = v2_stacked.unstack()
        
        return V2
        
       
        
                    
    def get_scenarios(self, market, scenario_type_list, source,
                      value_quantiles, hist_quantiles,
                      curve_fcst_date='last'):
        """
        

        Parameters
        ----------
        market : TYPE
            DESCRIPTION.
        days_forward : TYPE
            DESCRIPTION.
        source : TYPE
            DESCRIPTION.
         : TYPE
            DESCRIPTION.

        Returns
        -------
        None.
        
        Pseudo code:
            - get matrix of normalized values and nominal values
            - get normals matrix from nominal/normalized values
            - create changes of normalized values matrix
            - compute day ahead data from normalize values matrix
            - extract curve for scenarios generation (last by default of on given date)
            - for each hour on curve compute get scenario vector
            - from each scenario vector compute percentiles (10,25,50,75,90)
            - add each scenario change to normalized data and retrieve nominal data

        """
        start_time = time.time()
        # Get data
        nominal_matrix = self.data_dict[market]['nominal']
        normalized_matrix = self.data_dict[market]['normalized']
        
        # Get normal data
        normal_rld_matrix = self.data_dict[market]['normal']
        # Get changes of normlized data
        # changes_dict = self.get_hist_changes(days_fwd_list)
        
        changes_dict = {}
        for scenario_type in scenario_type_list:
            # day_shift = day - 1
            # shifted_data = normalized_matrix.shift(-day_shift).shift(day_shift*24,axis=1)
            # data_chng = shifted_data-normalized_matrix
            changes_dict[scenario_type] = self.get_hist_changes(scenario_type, normalized_matrix)
            
        # Get DA timeseries of normalized value
        da_data = self.get_da_data(normalized_matrix)
        # Get curves
        if curve_fcst_date in ['last']:
            curve_date = normalized_matrix.index[-1]
        else:
            curve_date = curve_fcst_date
        
        normalized_curve = normalized_matrix.loc[[curve_date]].copy()
        normal_curve = normal_rld_matrix.loc[[curve_date]].copy()
        
        # Get conditional values for the values in curve
        values_df = self.get_curve_values(normalized_curve, normalized_matrix,
                                           da_data.set_index('value_date').resample('D').\
                                               mean().rolling(14).mean().iloc[-1].values[0],
                                               value_quantiles=value_quantiles,
                                               hist_quantiles=hist_quantiles)
        
        # Get scenarios for day ahead
        # For scenario generatio there will be standalone function
        # There should be covered the cutoff date for matrix to compute the history
        scen_dict = {}
        for scenario_type in scenario_type_list:
            scen_dict[scenario_type] = self.get_scenarios_for_hour(market, scenario_type, curve_date,
                                                             normalized_curve, normal_curve,
                                                             values_df, changes_dict,
                                                             normalized_matrix)
        end_time = time.time()
        print(f"get_scenarios took {end_time - start_time} seconds to execute")
        return scen_dict
            
        
            
        
        
        
        

    
    
    def get_scenarios_for_hour(self, market, scenario_type, curve_date,
                               normalized_curve, normal_curve,
                               values_df,changes_dict,
                               normalized_matrix):
        start_time = time.time()
        # Automatically add 'real_value' index to scenario list
        # Get matrix of changes for given fwd_day
        change_matrix = changes_dict[scenario_type]
        # Adjust the matrix of values (matrix) and matrix of changes for curve date
        # Cut the matrices in date of curve to secure objective analysis of history for the given curve date
        normalized_matrix_adj = normalized_matrix.loc[:curve_date].iloc[:-1].copy()
        
        change_matrix_adj = change_matrix.loc[:curve_date].iloc[:-1].copy()
        # Adjust the value_ser for fwd_day shift (fwd_day*24)
        # shift_factor = ((fwd_day)*24)+1
        values_df_adj = values_df.loc[:,49:].copy()
        normalized_curve_adj = normalized_curve.loc[:,49:].copy()
        
        # Create empty scenario df for appending scenario percentiles
        # Loop through hours of value_series and get scenario distribution
        # and subsequent percentiles
        
        dist_params_list_final = []
        total_samples = []
        for i, hour in enumerate(values_df_adj.columns):
            if hour == 180:
                print('1996')
            
            curve_value = normalized_curve_adj[hour].iloc[0]
            values = values_df_adj[hour].to_list()
            masks_dict = self.get_mask(values,change_matrix_adj, normalized_matrix_adj, market)
           
            data_list = []
            
            for i, mask in masks_dict.items():            
                aux = change_matrix_adj[mask].copy()
                non_nan_mask = ~aux.isna()
                non_nan_values = aux[non_nan_mask].values.flatten()
                non_nan_values = non_nan_values[~np.isnan(non_nan_values)]
                if len(non_nan_values)==0:
                    raise ValueError('No data to use')
                # dist, dist_params = (self.fit_johnsonsu(non_nan_values))
                # # dist_list.append(dist)
                # dist_params_list.append((dist,dist_params))
                # data_list.append(non_nan_values)
                
           
                
            # unique_data = np.unique(list(itertools.chain.from_iterable(data_list)))
            # # Determine range based on quantiles
            # x_min, x_max = np.percentile(unique_data, [1, 99])  # 1st to 99th percentile
            # x_buffer = (x_max - x_min) * 0.10  # 10% buffer on each side
            # x = np.linspace(x_min - x_buffer, x_max + x_buffer, 1000)
            # bin_edges = np.histogram_bin_edges(unique_data, bins=x)
            
            # # hist_intersection = None
            # # for data in data_list:
            # #     aux_kde_samples = gaussian_kde(data).resample(1000).flatten()
            # #     hist, _ = np.histogram(data, x, )
            # #     if hist_intersection is None:
            # #         hist_intersection = aux_kde_samples
            # #     else:
            # #         hist_intersection = np.minimum(hist_intersection, aux_kde_samples)
                    
            # hist_intersection = None
            # for data in data_list:
            #     hist, _ = np.histogram(data, bins=x, density=True)
            #     if hist_intersection is None:
            #         hist_intersection = hist
            #     else:
            #         hist_intersection = np.minimum(hist_intersection, hist)
            
            # # Normalize the histogram to make it a probability distribution
            # hist_intersection /= np.sum(hist_intersection * np.diff(bin_edges))
            
            # # Compute the cumulative distribution function (CDF) from the histogram
            # cdf = np.cumsum(hist_intersection * np.diff(bin_edges))
            
            # # Function to perform inverse transform sampling
            # def inverse_transform_sampling(cdf, bin_edges, num_samples):
            #     # Generate uniform random samples
            #     random_samples = np.random.rand(num_samples)
            #     # Find where the random samples would go in the cdf
            #     sample_positions = np.searchsorted(cdf, random_samples) - 1
            #     # Interpolate in the bin_edges
            #     left_edges = bin_edges[sample_positions]
            #     right_edges = bin_edges[sample_positions + 1]
            #     # Compute actual sample values
            #     samples = left_edges + (random_samples - cdf[sample_positions]) * np.diff(bin_edges)[sample_positions] / (cdf[sample_positions + 1] - cdf[sample_positions])
            #     return samples
            
            # # Number of samples you want should be similar to the size of the original data
            # num_samples = len(np.concatenate(data_list))  # Total number of data points in the original datasets
            
            # # Generate samples from the intersection histogram
            # samples_from_hist = inverse_transform_sampling(cdf, bin_edges, 1000)
            # samples_from_hist = gaussian_kde(samples_from_hist).resample(1000).flatten()
            data = non_nan_values

            # Calculate Q1 (25th percentile) and Q3 (75th percentile)
            Q1 = np.percentile(data, 5)
            Q3 = np.percentile(data, 95)

            # Calculate IQR
            IQR = Q3 - Q1

            # Determine the whisker limits
            lower_whisker = Q1
            upper_whisker = Q3 

            # Filter the data to include only values within the whisker range
            filtered_data = data[(data >= lower_whisker) & (data <= upper_whisker)]
            samples_from_hist = gaussian_kde(filtered_data).resample(1000).flatten()
            total_samples.append(samples_from_hist)
                
            
            # dist_params_list_final.append(self.fit_johnsonsu(samples_from_hist))
            if ~non_nan_values.any():
                print('stop')
                
            
            
        
        datetime_index = normalized_curve.index[0] + pd.to_timedelta(values_df_adj.columns-1,unit='h')
        end_time = time.time()
        print(f"get_scenarios_for_hour took {end_time - start_time} seconds to execute")
        # return datetime_index, dist_params_list_final, curve_value, total_samples
        return pd.DataFrame(total_samples, index=datetime_index)
        # return dist_params_list
    
    @staticmethod
    def fit_johnsonsu(data):
        """
        Fits a Johnson SU distribution to the provided data.
    
        Parameters:
        data (array-like): The data to fit the Johnson SU distribution to.
    
        Returns:
        dist (rv_continuous): The Johnson SU distribution object fitted to the data.
        params (tuple): The parameters of the fitted Johnson SU distribution (a, b, loc, scale).
        """
        # Fit the Johnson SU distribution to the data
        params = johnsonsu.fit(data)
        a, b, loc, scale = params
        
        # Create the Johnson SU distribution object with the fitted parameters
        dist = johnsonsu(a, b, loc, scale)
        
        return dist, params

    @staticmethod
    def estimate_best_fit_distribution(data):
        """
        Fit a range of distributions to the data and return the best fitting one.
        
        :param data: 1D array of data points
        :return: Best fit distribution object and its parameters
        """
        start_time = time.time()
        distributions = [stats.norm, stats.expon, stats.lognorm, stats.weibull_min, stats.beta]
        best_fit_name = None
        best_fit_params = None
        best_fit_statistic = np.inf  # Start with infinity; lower values are better
        
        for distribution in distributions:
            # Fit distribution to data
            try:
                params = distribution.fit(data)
                arg = params[:-2]
                loc = params[-2]
                scale = params[-1]
    
                # Compute Kolmogorov-Smirnov test
                D, p_value = stats.kstest(data, distribution.name, args=params)
                
                if D < best_fit_statistic:  # Lower D statistic indicates better fit
                    best_fit_name = distribution.name
                    best_fit_params = params
                    best_fit_statistic = D
            except Exception:
                pass  # Handle errors in fitting
        
        # Return best fit distribution and its parameters
        best_distribution = getattr(stats, best_fit_name)
        # if 'norm' == best_fit_name:
        #     if best_fit_params[0] >2:
        #         print('1516')
        end_time = time.time()
        # print(f"estimate_best_fit_distribution took {end_time - start_time} seconds to execute")
        return best_distribution, best_fit_params
                            
            
    
    
    
    def get_transition_matrix(self, market, source,
                              curve_fcst_date='last', states=5, 
                              percentile_fix=500):
        start_time = time.time()
        # Get normalized data
        normalized_matrix = self.data_dict[market]['normalized']    
        # Get curves
        if curve_fcst_date in ['last']:
            curve_date = normalized_matrix.index[-1]
        else:
            curve_date = curve_fcst_date
            
        normalized_matrix_adj = normalized_matrix.loc[:curve_date].iloc[:-1].copy()
        
        # Get states (states are quantiles of normalized da values)
        state_series = self.rld_chng_mask(normalized_matrix_adj, normalized_matrix_adj, 'hist_position',
                                    quantiles=states, percentile_fix=percentile_fix,
                                    direct_output=True)['quantiles'].to_list()
        
        # Get unique states and sort them to maintain order
        unique_states = sorted(set(state_series))
        
        # Create a mapping of state to index to keep track of positions in the matrix
        state_index = {state: index for index, state in enumerate(unique_states)}
        
        # Initialize the transition matrix
        num_states = len(unique_states)
        transition_matrix = np.zeros((num_states, num_states))
        
        # Populate the transition matrix
        for (current_state, next_state) in zip(state_series, state_series[1:]):
            current_index = state_index[current_state]
            next_index = state_index[next_state]
            transition_matrix[current_index, next_index] += 1
        
        # Convert counts to probabilities
        transition_matrix = np.divide(transition_matrix, transition_matrix.sum(axis=1, keepdims=True))
        end_time = time.time()
        print(f"get_transition_matrix {end_time - start_time} seconds to execute")
        return transition_matrix

    
    def get_timeseries_scenarios(self, market, days_fwd_list, source,
                      curve_fcst_date='last', percentile_fix=500,
                      runs=200,
                      value_quantiles=10, hist_quantiles=3):
        
        start_time = time.time()
        
        # # Get raw data
        # normalized_data_raw = self.get_raw_data_normalized(market=market, source=source)
        # normalized_data_raw_smooth = self.get_raw_data_normalized(market=market, source=source,smooth=True)
        # nominal_data_raw = self.get_raw_data(market=market, source=source)
        # normal_data_raw = pd.merge(nominal_data_raw, normalized_data_raw,
        #                            on=['forecast_date', 'value_date'],
        #                            how='inner', suffixes=('_nominal', '_normal'))
        # normal_data_raw['rld'] = normal_data_raw['rld_nominal']/normal_data_raw['rld_normal']
        # normal_data_raw = normal_data_raw[['forecast_date', 'value_date', 'rld']].copy()
        
        # normal_data_raw_smooth = pd.merge(nominal_data_raw, normalized_data_raw_smooth,
        #                            on=['forecast_date', 'value_date'],
        #                            how='inner', suffixes=('_nominal', '_normal'))
        # normal_data_raw_smooth['rld'] = normal_data_raw_smooth['rld_nominal']/normal_data_raw_smooth['rld_normal']
        # normal_data_raw_smooth = normal_data_raw_smooth[['forecast_date', 'value_date', 'rld']].copy()
        
        self.compile_data(markets=[market])
        
        # Turn raw data to data matrix
        normalized_matrix = self.data_dict[market]['normalized']
        

        normal_matrix = self.data_dict[market]['normal']

        nominal_matrix = self.data_dict[market]['nominal']
        
        data_da = self.get_da_data(normalized_matrix)
        # Get curves
        if curve_fcst_date in ['last']:
            curve_date = normalized_matrix.index[-1]
        else:
            curve_date = curve_fcst_date
            
        normalized_matrix_adj = normalized_matrix.loc[:curve_date].iloc[:-1].copy()

        
        if market not in list(self.mask_dict):
            self.mask_dict[market] = {}
        if 'value_position' not in list(self.mask_dict[market]):
            self.rld_chng_mask(normalized_matrix_adj, normalized_matrix_adj, 'value_position',
                               market, value_quantiles=value_quantiles)
            
        quantiles = self.mask_dict[market]['value_position'].copy()
        days_change = quantiles.shape[1]//24
       
        transition_matrix = self.calculate_transition_matrix(self.get_da_data(quantiles), value_quantiles)
        
        scen_dict = self.get_scenarios(market=market,
                                            days_fwd_list=days_fwd_list,
                                            curve_fcst_date=curve_fcst_date,
                                            source=source,
                                            value_quantiles=value_quantiles,
                                            hist_quantiles=hist_quantiles)
        
        
        
        quantile_edge = self.get_quantile_edges(normalized_matrix_adj, value_quantiles)
        adjusted_quantile_edges = np.concatenate(([-np.inf], quantile_edge[1:-1], [np.inf]))
        
        normal_curve = normal_matrix.loc[curve_date].copy()
        
        nominal_curve = nominal_matrix.loc[curve_date].copy()
        
        quantile_samples_dict = {}
        for fwd_day in days_fwd_list:
            datetime_index = scen_dict[fwd_day][0]
            hours_index = (datetime_index[:-1] - curve_date).total_seconds()/3600
            mcmc_scenarios = []
            
            
            base_state_list = []
            start_time1 = time.time()
            for i, hour in enumerate(hours_index):
                
                normal_value = normal_curve[hour]
                nominal_value = nominal_curve[hour]
                # aux_dist, aux_params = scen_dict[fwd_day][1][i]
                aux_samples = scen_dict[fwd_day][3][i]

                
                kde = gaussian_kde(aux_samples)
                kde_samples = kde.resample(2000).flatten()
                # kde_samples_from_act = kde_samples * normal_value
                
                
                dist_states = np.unique([self.assign_quantile(a,adjusted_quantile_edges)
                                          for a in aux_samples+1])
                dist_states = np.unique([a if a<value_quantiles else value_quantiles-1 for a in dist_states])
                
                run_list = []
                base_state_aux = []

                for run in range(runs):
                    
                    if i == 0:
                        rand_draw = np.random.choice(kde_samples)
                        rand_draw_nominal = rand_draw * normal_value
                        run_list.append(rand_draw_nominal)
                        base_state = self.assign_quantile(rand_draw,
                                                          adjusted_quantile_edges)
                        base_state_aux.append(base_state)
                    else:
                                                
                        base_state = base_state_list[i-1][run]
                        
                        state_trans_prob = transition_matrix[base_state]
                        kde_samples_states = np.histogram(kde_samples,
                                                          bins=adjusted_quantile_edges)[0]
                        state_kde_prob = kde_samples_states/np.sum(kde_samples_states)
                        comb_prob = state_trans_prob*state_kde_prob
                        comb_prob = comb_prob/np.sum(comb_prob)
                        
                        next_state = np.random.choice(range(len(comb_prob)),p=comb_prob)
                        intervals = self.select_interval(next_state,adjusted_quantile_edges)
                        mask = ((kde_samples>=intervals[0]) &
                                (kde_samples<=intervals[1]))
                        rand_draw = np.random.choice(kde_samples[mask])
                        run_list.append(rand_draw*normal_value)
                        base_state_aux.append(next_state)
                        

                base_state_list.append(base_state_aux)
                mcmc_scenarios.append(run_list)
            end_time1 = time.time()
            print(f"run loop in get_timeseries_scenarios \
                  took {end_time1 - start_time1} seconds to execute")
            print(f"hour loop in get_timeseries_scenarios \
                  took {end_time1 - start_time1} seconds to execute")

            
        # Scenarios generation with
        
        scenarios_df = pd.DataFrame(np.array(mcmc_scenarios),
                                    index=datetime_index[:-1])
        end_time = time.time()
        print(f"get_timeseries_scenarios took {end_time - start_time} seconds to execute")
        return scenarios_df
    
    # def simulate_multiple_scenarios(self, markets=['de', 'fr', 'be', 'nl'],
    #                                 scenario_type_list=['liq'], curve_fcst_date='last', percentile_fix=500,
    #                                 scenario_list=[10,25,50,75,90],
    #                                 runs=1000, source='local', degrees_of_freedom=10,
    #                                 value_quantiles=10, hist_quantiles=3):
    #     def covariance_to_correlation(covariance_matrix):
    #         std_dev = np.sqrt(np.diag(covariance_matrix))
    #         correlation_matrix = covariance_matrix / np.outer(std_dev, std_dev)
    #         return correlation_matrix
    #     self.compile_data()
    #     # Get toghether day ahead data
    #     da_data = pd.DataFrame()
    #     for market in markets:
    #         aux_matrix_res = self.data_dict[market]['nominal']
    #         # aux_con_matrix = self.data_dict[market]['CON']
            
    #         aux_da = self.get_da_data(aux_matrix_res).set_index('value_date').iloc[-(8760*2):]
    #         if da_data.empty:
    #             da_data = aux_da.copy()
    #         else:
    #             da_data = pd.concat([da_data, aux_da], axis=1, join='inner')
        
    #     # Estimate covariance
    #     cov_dict = self.compute_hour_month_covariance(da_data)
            
        
    #     scen_dict = {}
    #     copula_dict = {}
    #     for scenario_type in scenario_type_list:
    #         # Generate scenarios for each market
    #         scen_dict[scenario_type] = {}
    #         for market_index, market in enumerate(markets):
    #             scen_dict[scenario_type][market] = {}
    #             normal_matrix = self.data_dict[market]['normal']
    #             con_matrix = self.data_dict[market]['CON']
    #             if curve_fcst_date in ['last']:
    #                 curve_date = normal_matrix.index[-1]
    #             else:
    #                 curve_date = curve_fcst_date

    #             single_scen_dict = self.get_scenarios(market, [scenario_type], source,
    #                                           value_quantiles, hist_quantiles,
    #                                           curve_fcst_date=curve_fcst_date)
    #             single_scen = single_scen_dict[scenario_type]
    #             normal_curve = normal_matrix[normal_matrix.index==curve_date].T.iloc[-len(single_scen.index):].copy()
    #             con_curve = con_matrix[con_matrix.index==curve_date].T.iloc[-len(single_scen.index):].copy()
    #             single_scen2 = pd.DataFrame((single_scen.values*normal_curve.values.reshape(-1,1)),
    #                                       index=single_scen.index).dropna()
    #             scen_dict[scenario_type][market]['scen'] = single_scen2
    #             scen_dict[scenario_type][market]['con_curve'] = con_curve
                
            
    #         copula_res = self.compute_joint_cdf_and_percentiles(scen_dict[scenario_type], cov_dict)
            
    #         for market in markets:
    #             con_curve = scen_dict[scenario_type][market]['con_curve']
    #             con_curve.index = con_curve.name + pd.to_timedelta(con_curve.index,unit='h')
    #             for percentile, percentile_df
            
                
    #     return copula_dict
    
    def simulate_multiple_scenarios(self, markets=['de', 'fr', 'be', 'nl'],
                                    scenario_type_list=['liq'], curve_fcst_date='last', percentile_fix=500,
                                    scenario_list=[10,25,50,75,90],
                                    runs=1000, source='local', degrees_of_freedom=10,
                                    value_quantiles=10, hist_quantiles=3):
        def covariance_to_correlation(covariance_matrix):
            std_dev = np.sqrt(np.diag(covariance_matrix))
            correlation_matrix = covariance_matrix / np.outer(std_dev, std_dev)
            return correlation_matrix
        self.compile_data()
        # Get toghether day ahead data
        da_data = pd.DataFrame()
        for market in markets:
            aux_matrix_res = self.data_dict[market]['nominal']
            aux_con_matrix = self.data_dict[market]['CON']
            aux_matrix_res_aligned, aux_con_matrix_aligned = aux_matrix_res.align(aux_con_matrix, join='inner', axis=1)
            aux_matrix_res_aligned, aux_con_matrix_aligned = aux_matrix_res_aligned.align(aux_con_matrix_aligned, join='inner', axis=0)
            aux_matrix = aux_con_matrix_aligned - aux_matrix_res_aligned
            aux_da = self.get_da_data(aux_matrix).set_index('value_date').iloc[-(8760*2):]
            if da_data.empty:
                da_data = aux_da.copy()
            else:
                da_data = pd.concat([da_data, aux_da], axis=1, join='inner')
        
        # Estimate covariance
        # cov_dict = self.compute_hour_month_covariance(da_data)
        
        tau_dict = self.compute_hour_month_kendall_tau(da_data)
            
        
        scen_dict = {}
        copula_dict = {}
        for scenario_type in scenario_type_list:
            # Generate scenarios for each market
            scen_dict[scenario_type] = {}
            for market_index, market in enumerate(markets):
                normal_matrix = self.data_dict[market]['normal']
                con_matrix = self.data_dict[market]['CON']
                if curve_fcst_date in ['last']:
                    curve_date = normal_matrix.index[-1]
                else:
                    curve_date = curve_fcst_date
                # single_scen = self.get_timeseries_scenarios(market, days_fwd_list, source=source,
                #                                             curve_fcst_date=curve_fcst_date)
                single_scen_dict = self.get_scenarios(market, [scenario_type], source,
                                              value_quantiles, hist_quantiles,
                                              curve_fcst_date=curve_fcst_date)
                single_scen = single_scen_dict[scenario_type]
                normal_curve = normal_matrix[normal_matrix.index==curve_date].T.iloc[-len(single_scen.index):].copy()
                con_curve = con_matrix[con_matrix.index==curve_date].T.iloc[-len(single_scen.index):].copy()
                single_scen2 = pd.DataFrame(con_curve.values.reshape(-1,1)-
                                          (single_scen.values*normal_curve.values.reshape(-1,1)),
                                          index=single_scen.index).dropna()
                # samples = []
                # index_list = []
                # for i, row in single_scen2.iterrows():
                #     dist_object = self.estimate_best_fit_distribution(row.values)
                #     market_uniform_samples = uniform_samples[:, market_inpd.DataFrame(con_curve.values.reshape(-1,1)-#                                       index=single_scen.index).dropna()dex]
                #     market_samples = self.sample_from_marginal(market_uniform_samples, dist_object)
                #     samples.append(market_samples)
                #     index_list.append(i)
                    
                # scen_dict[fwd_day][market] = samples, index_list
                scen_dict[scenario_type][market] = single_scen2
            copula_dict[scenario_type] = self.compute_joint_cdf_and_percentiles(scen_dict[scenario_type], tau_dict)
            
                
        return copula_dict
    
    @staticmethod
    def compute_joint_cdf(samples):
        n, d = samples.shape
        cdf_values = np.zeros_like(samples)
        
        # Compute the empirical CDF for each dimension
        for i in range(d):
            sorted_indices = np.argsort(samples[:, i])
            sorted_samples = samples[sorted_indices, i]
            cdf_values[sorted_indices, i] = np.arange(1, n + 1) / n
        
        return cdf_values

    def compute_perpendicular_products(self, samples):
        cdf_values = self.compute_joint_cdf(samples)
        
        # Compute the product of the CDF values for each sample
        products = np.prod(cdf_values, axis=1)
        
        return products

    def compute_quantile_clusters(self, samples, percentiles, vicinity=0.005):
        products = self.compute_perpendicular_products(samples)
        
        # Create a dictionary to store the points for each percentile
        all_clusters = {f'{int(p * 100)}th': [] for p in percentiles}
        
        # Sort samples by product values
        sorted_indices = np.argsort(products)
        sorted_products = products[sorted_indices]
        
        n = len(samples)
        
        # Assign quantiles based on the sorted product values
        for p in percentiles:
            lower_threshold_index = int(max((p - vicinity) * n, 0))
            upper_threshold_index = int(min((p + vicinity) * n, n))
            cluster_indices = sorted_indices[lower_threshold_index:upper_threshold_index]
            points = samples[cluster_indices]
            all_clusters[f'{int(p * 100)}th'].extend(points)
        
        return all_clusters

    def compute_joint_cdf_and_percentiles(self, scen_dict, tau_dict, df=10,
                                          percentiles=np.arange(2, 100, 2) / 100.0, num_points=5):
        def sample_from_empirical_distributions(means, tau_matrix, distributions, size):
            def compute_covariance_from_correlation(correlation_matrix, variances):
                # Construct a diagonal matrix of standard deviations
                std_devs = np.sqrt(variances)
                diagonal_matrix = np.diag(std_devs)
                
                # Multiply to get the covariance matrix: Cov = D * R * D
                covariance_matrix = diagonal_matrix @ correlation_matrix @ diagonal_matrix
                return covariance_matrix
            d = len(means)
            num_distributions = len(distributions)
    
            # Ensure there is one distribution per mean specified
            assert num_distributions == d, "The number of distributions must match the number of means."
    
            # Convert Kendall's tau to a correlation matrix suitable for generating samples
            # We use the sine approximation: rho = sin((pi/2) * tau)
            correlation_matrix = np.sin(np.pi / 2 * tau_matrix)
            variances = np.array([distributions[var].var() for var in range(len(distributions))])
            covariance_matrix = compute_covariance_from_correlation(correlation_matrix, variances)
    
            # Draw multivariate normal samples based on the transformed correlation matrix
            base_samples = np.random.multivariate_normal(np.zeros(d), covariance_matrix, size=size)
    
            # Initialize the array for the final samples
            final_samples = np.zeros((size, d))
    
            # For each dimension, resample from the empirical distribution based on the ranks of the normal samples
            for i in range(d):
                empirical_data = distributions[i]
                sorted_indices = np.argsort(empirical_data)
                # Convert base_samples to ranks and then to indices for empirical data
                ranks = np.argsort(np.argsort(base_samples[:, i]))
                resampled_indices = sorted_indices[ranks % len(empirical_data)]
                final_samples[:, i] = empirical_data[resampled_indices]
    
                # Adjust for the mean
                final_samples[:, i] += (means[i] - np.mean(empirical_data))
    
            return final_samples
    
        variables = list(scen_dict.keys())
        dates = scen_dict[variables[0]].index
        percentiles_dict = {}
    
        for ti, date in enumerate(dates):
            mean = np.array([scen_dict[var].iloc[ti, :].mean() for var in variables])
            distributions = [scen_dict[var].loc[date].values for var in variables]
    
            # Retrieve Kendall's tau matrix for the corresponding hour and month
            hour = date.hour
            month = date.month
            tau_matrix = tau_dict.get(f'hour_{hour}_month_{month}')
    
            if tau_matrix is not None and not tau_matrix.isnull().values.any():
                # Generate samples respecting the Kendall's tau matrix
                samples = sample_from_empirical_distributions(mean, tau_matrix, distributions, 1000)
                
                # Compute percentiles and store them
                for percentile in percentiles:
                    percentile_value = np.percentile(samples, percentile * 100, axis=0)
                    key = f'{int(percentile * 100)}th'
                    if key not in percentiles_dict:
                        percentiles_dict[key] = pd.DataFrame(index=dates, columns=variables)
                    percentiles_dict[key].loc[date] = percentile_value
    
        return percentiles_dict

    def compute_joint_cdf_and_percentiles(self, scen_dict, cov_dict, df=10,
                                          percentiles=np.arange(2, 100, 2) / 100.0,
                                          num_points=5):
        def sample_from_empirical_distributions(means, cov_matrix, distributions, size):
            d = len(means)
            num_distributions = len(distributions)
        
            # Ensure there is one distribution per mean specified
            assert num_distributions == d, "The number of distributions must match the number of means."
        
            # Draw multivariate normal samples based on the specified covariance matrix
            base_samples = np.random.multivariate_normal(np.zeros(d), cov_matrix, size=size)
        
            # Initialize the array for the final samples
            final_samples = np.zeros((size, d))
        
            # For each dimension, resample from the empirical distribution based on the ranks of the normal samples
            for i in range(d):
                empirical_data = distributions[i]
                sorted_indices = np.argsort(empirical_data)
                # Convert base_samples to ranks and then to indices for empirical data
                ranks = np.argsort(np.argsort(base_samples[:, i]))
                resampled_indices = sorted_indices[ranks % len(empirical_data)]
                final_samples[:, i] = empirical_data[resampled_indices]
                
                # Adjust for the mean
                final_samples[:, i] += (means[i] - np.mean(empirical_data))
        
            return final_samples

        # Extract variables and data
        variables = list(scen_dict.keys())
        data = {var: scen_dict[var] for var in variables}
        dates = scen_dict[variables[0]].index

        # Initialize the percentiles dictionary
        # percentiles_dict = {f'{int(p * 100)}th_comb_{i}': pd.DataFrame(index=dates, columns=variables) for p in percentiles for i in range(num_points)}
        percentiles_dict = {}
        for ti, date in enumerate(dates):
            # Calculate mean and skewness for each variable at this time point
            mean = np.array([data[var].iloc[ti, :].mean() for var in variables])
            skewness = np.array([skew(data[var].iloc[ti, :]) for var in variables])
            
            # Retrieve covariance matrix for the corresponding hour and month
            hour = date.hour
            month = date.month
            cov_matrix = cov_dict.get(f'hour_{hour}_month_{month}')
            distributions = [data[var].loc[date].values for var in variables]
            
            if cov_matrix is not None and not cov_matrix.isnull().values.any():
                # Generate skewed t-distribution samples
                samples = sample_from_empirical_distributions(mean,
                                                              cov_matrix,
                                                              distributions,
                                                              1000)
    
                # Compute the quantile clusters
                all_clusters = self.compute_quantile_clusters(samples, percentiles)
    
                # Store selected points in the percentiles_dict
                for percentile, points in all_clusters.items():
                    for i, point in enumerate(points):
                        key = f'{percentile}_comb_{i}'
                        if key not in percentiles_dict:
                            percentiles_dict[key] = pd.DataFrame(index=dates, columns=variables)
                        percentiles_dict[key].loc[date] = point

        return percentiles_dict
    
    
    # @staticmethod
    # def compute_joint_cdf_and_percentiles(scen_dict, cov_matrix, df=10,
    #                                       percentiles=np.arange(2, 100, 2) / 100.0,
    #                                       num_points=5):
    #     def skew_t_rvs(mean, cov_matrix, df, skewness, size):
    #         d = len(mean)
    #         gamma = np.tile(skewness, (size, 1))
    #         delta = np.sqrt(df / (df - 2)) * np.linalg.cholesky(cov_matrix).T @ gamma.T
    #         samples = multivariate_t.rvs(mean, cov_matrix, df, size)
    #         skewed_samples = samples + delta.T
    #         return skewed_samples
    
    #     # Extract variables and data
    #     variables = list(scen_dict.keys())
    #     data = {var: scen_dict[var] for var in variables}
    #     dates = scen_dict[variables[0]].index
    
    #     # Initialize the percentiles dictionary
    #     percentiles_dict = {f'{int(p * 100)}th_comb_{i}': pd.DataFrame(index=dates, columns=variables) for p in percentiles for i in range(num_points)}
    
    #     for t, date in enumerate(dates):
    #         # Calculate mean and skewness for each variable at this time point
    #         mean = np.array([data[var].iloc[t, :].mean() for var in variables])
    #         skewness = np.array([skew(data[var].iloc[t, :]) for var in variables])
    
    #         # Generate skewed t-distribution samples
    #         samples = skew_t_rvs(mean, cov_matrix, df, skewness, 1000)
    
    #         # Compute the ECDF for each variable
    #         ecdfs = {var: ECDF(data[var].iloc[t, :]) for var in variables}
    
    #         all_points = {f'{int(p * 100)}th': [] for p in percentiles}
    #         for p in percentiles:
    #             # Find the grid points closest to the specified percentile
    #             target_percentile = np.percentile(samples, p * 100, axis=0)
    #             distances = np.linalg.norm(samples - target_percentile, axis=1)
    #             closest_indices = np.argsort(distances)[:num_points]
    #             points = samples[closest_indices]
    #             all_points[f'{int(p * 100)}th'].extend(points)
    
    #         # Store selected points in the percentiles_dict
    #         for percentile, points in all_points.items():
    #             for i, point in enumerate(points):
    #                 percentiles_dict[f'{percentile}_comb_{i}'].loc[date] = point
    
    #     return percentiles_dict
    
    @staticmethod
    def compute_hour_month_covariance(time_series):
        # Initialize a dictionary to store covariance matrices
        covariance_dict = {}
        
        # Extract hour and month from the datetime index
        time_series['hour'] = time_series.index.hour
        time_series['month'] = time_series.index.month
        
        # Group by hour and month and compute the covariance matrix for each group
        for hour in range(24):
            for month in range(1, 13):
                # Filter the data for the current hour and month
                subset = time_series[(time_series['hour'] == hour) & (time_series['month'] == month)]
                
                # Compute the covariance matrix if there are enough data points
                if len(subset) > 1:
                    covariance_matrix = subset.drop(['hour', 'month'], axis=1).cov()
                    covariance_dict[f'hour_{hour}_month_{month}'] = covariance_matrix
                else:
                    covariance_dict[f'hour_{hour}_month_{month}'] = None
        
        return covariance_dict
    
    
    @staticmethod
    def compute_hour_month_kendall_tau(time_series):
        # Initialize a dictionary to store Kendall's Tau correlation matrices
        tau_dict = {}
    
        # Extract hour and month from the datetime index
        time_series['hour'] = time_series.index.hour
        time_series['month'] = time_series.index.month
        
        # Group by hour and month and compute the Kendall's Tau correlation matrix for each group
        for hour in range(24):
            for month in range(1, 13):
                # Filter the data for the current hour and month
                subset = time_series[(time_series['hour'] == hour) & (time_series['month'] == month)]
                
                # Compute the Kendall's Tau correlation matrix if there are enough data points
                if len(subset) > 1:
                    tau_matrix = subset.drop(['hour', 'month'], axis=1).corr(method='kendall')
                    tau_dict[f'hour_{hour}_month_{month}'] = tau_matrix
                else:
                    tau_dict[f'hour_{hour}_month_{month}'] = None
        
        return tau_dict
        
    
    # @staticmethod
    # def compute_joint_cdf_and_percentiles(scen_dict, cov_matrix, df=10,
    #                                       percentiles=np.arange(2, 100, 2) / 100.0,
    #                                       num_points=5):
    #     def skew_t_rvs(mean, cov_matrix, df, skewness, size):
    #         d = len(mean)
    #         gamma = np.tile(skewness, (size, 1))
    #         delta = np.sqrt(df / (df - 2)) * np.linalg.cholesky(cov_matrix).T @ gamma.T
    #         samples = multivariate_t.rvs(mean, cov_matrix, df, size)
    #         skewed_samples = samples + delta.T
    #         return skewed_samples
    
    #     # Extract variables and data
    #     variables = list(scen_dict.keys())
    #     data = {var: scen_dict[var] for var in variables}
    #     dates = scen_dict[variables[0]].index
    
    #     # Initialize the percentiles dictionary
    #     percentiles_dict = {f'{int(p * 100)}th_comb_{i}': pd.DataFrame(index=dates, columns=variables) for p in percentiles for i in range(num_points)}
    
    #     for t, date in enumerate(dates):
    #         # Calculate mean and skewness for each variable at this time point
    #         mean = np.array([data[var].iloc[t, :].mean() for var in variables])
    #         skewness = np.array([skew(data[var].iloc[t, :]) for var in variables])
    
    #         # Generate skewed t-distribution samples
    #         samples = skew_t_rvs(mean, cov_matrix, df, skewness, 200)
    
    #         # Compute the ECDF for each variable
    #         ecdfs = {var: ECDF(data[var].iloc[t, :]) for var in variables}
    
    #         all_points = {f'{int(p * 100)}th': [] for p in percentiles}
    #         for p in percentiles:
    #             # Find the grid points closest to the specified percentile
    #             target_percentile = np.percentile(samples, p * 100, axis=0)
    #             distances = np.linalg.norm(samples - target_percentile, axis=1)
    #             closest_indices = np.argsort(distances)[:num_points]
    #             points = samples[closest_indices]
    #             all_points[f'{int(p * 100)}th'].extend(points)
    
    #         # Store selected points in the percentiles_dict
    #         for percentile, points in all_points.items():
    #             for i, point in enumerate(points):
    #                 percentiles_dict[f'{percentile}_comb_{i}'].loc[date] = point
    
    #     return percentiles_dict
    
    # def compute_joint_cdf_and_percentiles(scen_dict, cov_matrix,
    #                                       percentiles=np.arange(10, 100, 10) / 100.0, tolerance=0.01, num_points=10):
    #     # Extract variables and data
    #     variables = list(scen_dict.keys())
    #     data = {var: scen_dict[var].values for var in variables}
    #     dates = scen_dict[variables[0]].index
    
    #     # Initialize the percentiles dictionary
    #     percentiles_dict = {date: {f'{int(p * 100)}th': pd.DataFrame(columns=variables) for p in percentiles} for date in dates}
    
    #     # Compute joint CDF and select percentiles for each time point
    #     for t, date in enumerate(dates):
    #         # Create linspace for each variable at this time point
    #         linspace_dict = {var: np.linspace(data[var][t, :].min(), data[var][t, :].max(), 100) for var in variables}
    
    #         # Create a meshgrid for evaluating the joint CDF
    #         meshgrid = np.meshgrid(*[linspace_dict[var] for var in variables])
    #         grid_shape = meshgrid[0].shape
    
    #         # Initialize joint CDF array
    #         joint_cdf = np.zeros(grid_shape)
    
               
    #         # Flatten the grid for easier manipulation
    #         grid_points = np.array([mg.flatten() for mg in meshgrid]).T
    #         # Calculate the joint CDF in a vectorized manner
    #         conditions = np.ones((grid_points.shape[0], data[variables[0]].shape[1]), dtype=bool)
    #         for i, var in enumerate(variables):
    #             conditions &= (data[var][t, :] <= grid_points[:, i].reshape(-1, 1))
    #         joint_cdf = np.mean(conditions, axis=1).reshape(grid_shape)
    
    #         # Find all the points closest to the specified percentiles
    #         all_points = {f'{int(p * 100)}th': [] for p in percentiles}
    #         for target_percentile in percentiles:
    #             close_points = np.where(np.abs(joint_cdf - target_percentile) <= tolerance)
    #             for idx in zip(*close_points):
    #                 point = tuple(linspace_dict[var][idx[i]] for i, var in enumerate(variables))
    #                 all_points[f'{int(target_percentile * 100)}th'].append(point)
    
    #         # Select evenly spaced points from each percentile
    #         selected_points = {}
    #         for percentile, points in all_points.items():
    #             if points:
    #                 points_array = np.array(points)
    #                 sorted_indices = np.argsort(points_array[:, 0])  # Sort based on the first variable
    #                 sorted_points = points_array[sorted_indices]
    #                 step = max(1, len(sorted_points) // num_points)
    #                 selected_indices = np.arange(0, len(sorted_points), step)[:num_points]
    #                 selected_points[percentile] = sorted_points[selected_indices]
    #             else:
    #                 selected_points[percentile] = np.array(points)
    
    #         # Store selected points in the percentiles_dict
    #         for percentile, points in selected_points.items():
    #             percentiles_dict[date][percentile] = pd.DataFrame(points, columns=variables)
    
    #     return percentiles_dict
    
    # @staticmethod
    # def compute_and_sample_copula(scen_dict, cov, runs=100, degrees_of_freedom=10):
    #     combined_percentiles = {}

    #     # Compute percentiles for each variable
    #     for var, df in scen_dict.items():
    #         percentiles = np.arange(10, 100, 10)  # 10th, 20th, ..., 90th percentiles
    #         percentiles_df = df.apply(lambda x: np.percentile(x, percentiles), axis=1, result_type='expand')
    #         percentiles_df.columns = percentiles
    #         combined_percentiles[var] = percentiles_df

    #     # Combine all percentile DataFrames into one
    #     combined_percentiles_df = pd.concat(combined_percentiles, axis=1)
        
    #     # Generate copula samples for each percentile
    #     def generate_copula_samples(combined_percentiles_df, cov, runs):
    #         sampled_combinations = {}

    #         for percentile in np.arange(10, 100, 10):
    #             percentiles_at_time_point = combined_percentiles_df.loc[:, (slice(None), percentile)]
    #             mean = percentiles_at_time_point.mean().values

    #             # Generate uniform samples using the copula
    #             mvn = multivariate_t(loc=mean, shape=cov, df=degrees_of_freedom)
    #             u_samples = mvn.rvs(size=runs)

    #             # Ensure samples are within the [0, 1] range
    #             u_samples = np.clip(u_samples, 0, 1)

    #             # Apply the inverse CDF of the marginals using ECDF
    #             sample_dict = {}
    #             for var, df in scen_dict.items():
    #                 ecdf = ECDF(df.values.flatten())
    #                 inverse_cdf = np.interp(u_samples[:, list(scen_dict.keys()).index(var)], ecdf.y, ecdf.x)
    #                 sample_dict[var] = inverse_cdf

    #             sampled_combinations[f'percentile_{percentile}'] = pd.DataFrame(sample_dict)

    #         return sampled_combinations
    
    #     all_copula_samples = generate_copula_samples(combined_percentiles_df, cov, runs)
    
    #     return all_copula_samples
    
    
    
    # @staticmethod
    # def compute_and_sample_copula(scen_dict, cov, runs=100, degrees_of_freedom=10):
    #     combined_percentiles = {}

    #     # Compute percentiles for each variable
    #     for var, df in scen_dict.items():
    #         percentiles = np.arange(10, 100, 10)  # 10th, 20th, ..., 90th percentiles
    #         percentiles_df = df.apply(lambda x: np.percentile(x, percentiles), axis=1, result_type='expand')
    #         percentiles_df.columns = percentiles
    #         combined_percentiles[var] = percentiles_df

    #     # Combine all percentile DataFrames into one
    #     combined_percentiles_df = pd.concat(combined_percentiles, axis=1)

    #     # Generate copula samples for each percentile
    #     def generate_copula_samples(combined_percentiles_df, cov, runs):
    #         sampled_combinations = {f'percentile_{p}': [] for p in np.arange(10, 100, 10)}

    #         for percentile in np.arange(10, 100, 10):
    #             percentiles_at_time_point = combined_percentiles_df.loc[:, (slice(None), percentile)]
    #             mean = percentiles_at_time_point.mean().values

    #             # Generate uniform samples using the copula
    #             mvn = multivariate_t(loc=mean, shape=cov, df=degrees_of_freedom)
    #             u_samples = mvn.rvs(size=runs)

    #             # Normalize the samples to [0, 1]
    #             u_samples = (u_samples - u_samples.min()) / (u_samples.max() - u_samples.min())

    #             # Apply the inverse CDF of the marginals using ECDF
    #             sample_dict = {}
    #             for var, df in scen_dict.items():
    #                 ecdf = ECDF(df.values.flatten())
    #                 inverse_cdf = np.interp(u_samples[:, list(scen_dict.keys()).index(var)], ecdf.y, ecdf.x)
    #                 sample_dict[var] = inverse_cdf

    #             sampled_combinations[f'percentile_{percentile}'] = pd.DataFrame(sample_dict)

    #         return sampled_combinations
    
    #     all_copula_samples = generate_copula_samples(combined_percentiles_df, cov, runs)
    
    #     return all_copula_samples
    
    # @staticmethod
    # def compute_and_sample_copula(scen_dict, cov, runs, degrees_of_freedom=10):
    #     combined_percentiles = {}
    
    #     for var, df in scen_dict.items():
    #         percentiles = np.arange(1, 100)
    #         percentiles_df = df.apply(lambda x: np.percentile(x, percentiles), axis=1)
    #         combined_percentiles[var] = percentiles_df
    
    #     # Combine all percentile DataFrames into one
    #     combined_percentiles_df = pd.concat(combined_percentiles, axis=1)
    
    #     # Function to fit a t-Copula and generate samples
    #     def generate_copula_samples(combined_percentiles_df, df, cov):
    #         n_samples = runs
    #         all_samples_dict = {f'sample_{i+1}': pd.DataFrame(index=combined_percentiles_df.index, columns=combined_percentiles_df.columns) for i in range(n_samples)}
    
    #         for i in range(len(combined_percentiles_df)):
    #             # Extract the percentiles for the current time point
    #             percentiles_at_time_point = pd.DataFrame()
    #             for var, var_arr in combined_percentiles_df.iloc[i].items():
    #                 if percentiles_at_time_point.empty:
    #                     percentiles_at_time_point = pd.DataFrame(var_arr, columns=[var])
    #                 else:
    #                     percentiles_at_time_point = pd.concat([percentiles_at_time_point,
    #                                                             pd.DataFrame(var_arr, columns=[var])],
    #                                                           axis=1)
    
    #             # Fit the t-Copula
    #             mean = percentiles_at_time_point.mean().values
    
    #             # Generate samples
    #             rvs = multivariate_t.rvs(mean, cov, df, size=n_samples)
    
    #             # Populate the all_samples_dict
    #             for j in range(n_samples):
    #                 all_samples_dict[f'sample_{j+1}'].iloc[i] = rvs[j]
    
    #         return all_samples_dict
    
    #     # Generate copula samples for each time point
    #     all_copula_samples = generate_copula_samples(combined_percentiles_df, degrees_of_freedom, cov)
    
    #     return all_copula_samples
    
    # @staticmethod
    # def compute_and_sample_copula(scen_dict, cov, degrees_of_freedom=10):
    #     all_scen_percentile_pairs = {}
    

    #     combined_percentiles = {}
        
    #     for var, df in scen_dict.items():
    #         percentiles = np.arange(1, 100)
    #         percentiles_df = df.apply(lambda x: np.percentile(x, percentiles), axis=1)
    #         combined_percentiles[var] = percentiles_df
        
    #     # Combine all percentile DataFrames into one
    #     combined_percentiles_df = pd.concat(combined_percentiles, axis=1)
            
    #     # Function to fit a t-Copula and generate specific percentiles
    #     def generate_percentile_pairs(combined_percentiles_df, df, cov):
    #         all_percentile_pairs = {p: [] for p in range(1, 100)}
            
    #         for i in range(len(combined_percentiles_df)):
    #             # Extract the percentiles for the current time point
    #             percentiles_at_time_point = pd.DataFrame()
    #             for var, var_arr in combined_percentiles_df.iloc[i].items():
    #                 if percentiles_at_time_point.empty:
    #                     percentiles_at_time_point = pd.DataFrame(var_arr,columns=[var])
    #                 else:
    #                     percentiles_at_time_point = pd.concat([percentiles_at_time_point,
    #                                                            pd.DataFrame(var_arr,columns=[var])],
    #                                                           axis=1)
                
    #             # Fit the t-Copula
    #             mean = percentiles_at_time_point.mean().values
    #             # cov = percentiles_at_time_point.cov().values
                
    #             # Generate samples
    #             n_samples = 10000
    #             rvs = multivariate_t.rvs(mean, cov, df, size=n_samples)
                
    #             # Standardize the samples
    #             standardized_rvs = (rvs - mean) / np.sqrt(np.diag(cov))
                
    #             # Convert samples to percentiles
    #             sampled_percentiles = t.cdf(standardized_rvs, df)
                
    #             # Calculate the empirical CDF value for each sample
    #             joint_cdf = np.mean(sampled_percentiles, axis=1)
                
    #             # Sort samples by their joint CDF value
    #             sorted_indices = np.argsort(joint_cdf)
    #             sorted_rvs = rvs[sorted_indices]
                
    #             for p in range(1, 100):
    #                 # Get the sample corresponding to the desired percentile
    #                 index = int((p / 100.0) * n_samples) - 1
    #                 percentile_values = sorted_rvs[index]
    #                 all_percentile_pairs[p].append(percentile_values)
            
    #         return {p: pd.DataFrame(values, columns=percentiles_at_time_point.columns, index=combined_percentiles_df.index) for p, values in all_percentile_pairs.items()}

    #     # Generate percentile pairs for each time point from 1st to 99th
    #     all_percentile_pairs = generate_percentile_pairs(combined_percentiles_df, degrees_of_freedom, cov)
    #     # all_scen_percentile_pairs[scenario] = all_percentile_pairs
    
    #     return all_percentile_pairs
                    
    @staticmethod
    def calculate_transition_matrix(time_series, num_states):
        """
        Vectorized version to calculate the transition matrix from a given time series of states.
    
        Parameters:
        - time_series: pd.Series or np.array, the time series of states. If pd.Series, assumes index is 'value_date'.
        - num_states: int, the number of unique states.
    
        Returns:
        - A 2D numpy array representing the transition probability matrix.
        """
        # If time_series is a pandas Series, convert to numpy array
        if isinstance(time_series, pd.Series):
            time_series = time_series.values
        elif isinstance(time_series, pd.DataFrame):
            time_series = time_series.set_index('value_date').values
        
        # Ensure the time series is an integer type and handle NaNs
        time_series = np.clip(time_series.astype(int), 0, num_states - 1)
        
        # Prepare arrays of current states and next states
        current_states = time_series[:-1]
        next_states = time_series[1:]
        
        # Use np.add.at to count transitions
        transition_counts = np.zeros((num_states, num_states), dtype=int)
        np.add.at(transition_counts, (current_states, next_states), 1)
        
        # Calculate transition probabilities
        transition_probabilities = np.divide(
            transition_counts,
            transition_counts.sum(axis=1, keepdims=True),
            out=np.zeros_like(transition_counts, dtype=float),
            where=transition_counts.sum(axis=1, keepdims=True) != 0
        )
        
        return transition_probabilities
        # """
        # Calculates the transition matrix from a given time series of states.
        
        # Parameters:
        # - time_series: np.array, the time series of states.
        # - num_states: int, the number of unique states.
        
        # Returns:
        # - A 2D numpy array representing the transition probability matrix.
        # """
        # # Ensure the time series is an integer type and handle NaNs
        # time_series = np.clip(time_series.set_index('value_date').fillna(num_states - 1).astype(int),
        #                                0, num_states - 1).values
        
        # # Initialize the count matrix
        # transition_counts = np.zeros((num_states, num_states), dtype=int)
        
        # # Count transitions
        # for i in range(len(time_series) - 1):
        #     current_state = time_series[i]
        #     next_state = time_series[i + 1]
        #     transition_counts[current_state, next_state] += 1
        
        # # Calculate transition probabilities
        # transition_probabilities = np.divide(
        #     transition_counts,
        #     transition_counts.sum(axis=1, keepdims=True),
        #     out=np.zeros_like(transition_counts, dtype=float),
        #     where=transition_counts.sum(axis=1, keepdims=True) != 0
        # )
        
        # return transition_probabilities
    
    @staticmethod
    def sample_uniform_from_copula(num_samples, dimensions, df, correlation_matrix):
        # This is a placeholder for your copula sampling method
        copula_samples = multivariate_t.rvs(loc=np.zeros(dimensions),
                                            shape=correlation_matrix, df=df, size=num_samples)
        uniform_samples = t.cdf(copula_samples, df=df, loc=0, scale=1)
        return uniform_samples
    
    @staticmethod
    def sample_from_marginal(uniform_sample, dist_object_param):
        """
        Transform a uniform sample to a target distribution using the .ppf method of the distribution.
        
        :param uniform_sample: Array of uniform samples from a copula for a single variable.
        :param dist_object_param: Tuple containing a distribution object and its parameters.
        :return: Array of samples transformed to the target distribution.
        """
        dist, params = dist_object_param
        # Special handling for the Beta distribution due to its parameter structure
        if dist.name == 'beta':
            # Ensure 'a' and 'b' are correctly positioned
            a, b, loc, scale = params
            transformed_sample = dist.ppf(uniform_sample, a, b, loc=loc, scale=scale)
        else:
            # Extract parameters for other distributions
            arg = params[:-2]
            loc = params[-2]
            scale = params[-1]
            transformed_sample = dist.ppf(uniform_sample, *arg, loc=loc, scale=scale)
        return transformed_sample
    
    @staticmethod
    def select_interval(quantile_value, edges):
        """
        Selects the interval corresponding to a given quantile value based on quantile edges.
        
        :param quantile_value: The given quantile value (e.g., 0, 1, 2, 3...).
        :param edges: The adjusted quantile edges including -np.inf and np.inf.
        :return: A tuple representing the interval (lower_bound, upper_bound).
        """
        # Edge cases for the first and last quantiles
        if quantile_value == 0:
            return (edges[0], edges[1])  # Interval for the 0th quantile
        elif quantile_value == len(edges) - 2:
            return (edges[-2], edges[-1])  # Interval for the last quantile
        else:
            # Interval for other quantiles
            return (edges[quantile_value], edges[quantile_value + 1])
    
    @staticmethod
    def assign_quantile(value, edges):
        """
        Assigns a quantile index to a value based on quantile edges.
        
        :param value: The value to assign a quantile index to.
        :param edges: The trimmed quantile edges.
        :return: The quantile index, where 0 is below the first edge and 
                 len(edges) is above the last edge.
        # """
        # # Check if the value is below the lowest edge
        # if value < edges[0]:
        #     return 0
        # # Check if the value is above the highest edge
        # elif value > edges[-1]:
        #     return len(edges)
        # Find the intermediate quantile
        for i, edge in enumerate(edges):
            if value < edge:
                return i-1  # Plus one because we start counting quantiles from 1 between edges
        # Fallback, should not happen
        return -1
        
    # @staticmethod
    # def get_quantile_edges(normalized_matrix_adj, tot_quantiles):
    #     quantile_edges = {}
        
    #     # Quantiles to compute
    #     quantiles = np.linspace(0,1,tot_quantiles+1)
        
    #     # Compute quantile bin edges for each column
    #     for column in normalized_matrix_adj:
    #         # Calculate the quantiles for this column
    #         quantile_values = np.quantile(normalized_matrix_adj[column].dropna(), quantiles)
    #         # Store the results
    #         quantile_edges[column] = quantile_values
            
    #     return quantile_edges
    
    
    def get_quantile_edges(self, normalized_matrix_adj, tot_quantiles):
        data_da = self.get_da_data(normalized_matrix_adj).set_index('value_date').dropna().values
        quantiles = np.linspace(0,1,tot_quantiles+1)
        
        quant_edges = np.quantile(data_da,quantiles)
        return quant_edges
    
            
    @staticmethod
    def sample_from_truncated_kde(data, interval, num_samples=1000):
        """
        Sample from a truncated KDE distribution.
        
        :param data: Array-like, empirical data used to create the KDE.
        :param interval: Tuple (min, max) specifying the interval to sample from.
                         Use np.inf or -np.inf for unbounded intervals.
        :param num_samples: Number of samples to generate.
        :return: Array of samples.
        """
        # Create KDE from the data
        kde = gaussian_kde(data, bw_method=0.5)
    
        # Define the interval
        min_val, max_val = interval
    
        # Function to generate samples and filter them based on the interval
        def generate_samples_within_interval(kde, min_val, max_val, num_samples):
            samples = kde.resample(num_samples * 2).flatten()  # Generate more samples to ensure enough within the interval
            if not np.isinf(min_val):
                samples = samples[samples >= min_val]
            if not np.isinf(max_val):
                samples = samples[samples <= max_val]
            return samples
    
        # Generate an initial batch of samples
        oversample_factor = 5
        initial_num_samples = int(num_samples * oversample_factor)
        samples = generate_samples_within_interval(kde, min_val, max_val, initial_num_samples)
    
        # Ensure we have enough samples by generating more if necessary
        if len(samples) < num_samples:
            additional_samples = generate_samples_within_interval(kde, min_val, max_val, initial_num_samples)
            samples = np.concatenate((samples, additional_samples))
    
        # Select only the number of samples required
        return samples[:num_samples]
    
    @staticmethod
    def sample_from_truncated_empirical_distribution(data, interval, num_samples=1000):
        """
        Sample from a truncated empirical distribution using the empirical CDF.
        
        :param data: Array-like, empirical data used to create the CDF.
        :param interval: Tuple (min, max) specifying the interval to sample from.
                         Use np.inf or -np.inf for unbounded intervals.
        :param num_samples: Number of samples to generate.
        :return: Array of samples.
        """
        # Filter data within the specified interval
        if not np.isinf(interval[0]):
            data = data[data >= interval[0]]
        if not np.isinf(interval[1]):
            data = data[data <= interval[1]]
    
        # Sort the filtered data
        sorted_data = np.sort(data)
    
        # Generate random uniform values
        random_uniforms = np.random.rand(num_samples)
    
        # Map uniform values to indices
        indices = np.floor(random_uniforms * len(sorted_data)).astype(int)
    
        # Handle edge case where index equals length of sorted_data
        indices[indices == len(sorted_data)] = len(sorted_data) - 1
    
        # Return the sampled values
        return sorted_data[indices]
    
    @staticmethod
    def sample_from_truncated_empirical_distribution2(data, interval, num_samples=1000):
        """
        Sample from a truncated empirical distribution using KDE.
        
        :param data: Array-like, empirical data used to estimate the distribution.
        :param interval: Tuple (min, max) specifying the interval to sample from.
                         Use np.inf or -np.inf for unbounded intervals.
        :param num_samples: Number of samples to generate.
        :return: Array of samples.
        """
        # Fit KDE to the data
        kde = gaussian_kde(data)

        # Adjust for open-ended intervals
        lower_bound = -np.inf if np.isinf(interval[0]) else interval[0]
        upper_bound = np.inf if np.isinf(interval[1]) else interval[1]

        # Fine-grained x for the range of data and KDE evaluation
        x = np.linspace(min(data), max(data), 1000)
        x = x[(x >= lower_bound) & (x <= upper_bound)]
        
        # Evaluate the KDE over this range
        pdf_values = kde(x)
        pdf_values /= pdf_values.sum()  # Normalize the probabilities

        # Build the CDF from the KDE
        cdf = np.cumsum(pdf_values)
        cdf /= cdf[-1]  # Ensure CDF goes to 1

        # Generate uniform samples in the CDF range and transform back using inverse CDF
        random_values = np.random.rand(num_samples)
        sample_indices = np.searchsorted(cdf, random_values)
        sample_values = x[sample_indices]

        return sample_values
    
    @staticmethod
    def sample_from_truncated_distribution(dist_type, dist_params, interval, num_samples=1000):
        """
        Sample from a truncated distribution specified by type and parameters.
        Allows for open-ended intervals by setting interval values to np.inf or -np.inf.
        
        :param dist_type: Type of the distribution, e.g., stats.norm, stats.weibull_min.
        :param dist_params: Parameters required for the distribution.
        :param interval: Tuple (min, max) specifying the interval to sample from.
                         Use np.inf or -np.inf for unbounded intervals.
        :param num_samples: Number of samples to generate.
        :return: Array of samples.
        """
        # Adjust CDF calculations for open-ended intervals
        cdf_lower = 0 if np.isinf(interval[0]) else dist_type.cdf(interval[0], *dist_params)
        cdf_upper = 1 if np.isinf(interval[1]) else dist_type.cdf(interval[1], *dist_params)
        if cdf_upper == cdf_lower:
            print('1852')
        # Generate uniform samples in the CDF range and transform back using the PPF
        uniform_samples = np.random.uniform(cdf_lower, cdf_upper, num_samples)
        return dist_type.ppf(uniform_samples, *dist_params)


        
    
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
        if 'level_0' in out_df.columns:
            out_df.columns = ['hours', 'forecast_date', 0]
        out_df['value_date'] = out_df['forecast_date'] + pd.to_timedelta(out_df['hours']-1, unit='h')
        out_df = out_df.sort_values('value_date')
        out_df = out_df.loc[((out_df['hours']>24)&
                             (out_df['hours']<49))].copy()
        out_df = out_df[['value_date', 0]].copy()
        out_df = out_df.rename(columns={0: 'rld_da'})
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
    
    
    am_inst = AvCapMonitor()
    
    am_inst.set_date_range(dt.datetime(2020,1,1), dt.datetime(2024,9,19))
    
    inst_da = am_inst.get_data_da(fund_type='InstCap', source='db')
    
    # sD = dt.datetime(2015,1,1)
    # eD = dt.datetime(2024,1,1)
    # market ='de'
    
    # mon_inst = SettleMonitor()
    # mon_inst.set_date_range(sD, eD)
    # mon_inst.set_grids(['de'])
    
    # spread_list = ['Q_2', 'Q_3']
    # spread = mon_inst.process_spread(spread_list, 'base')
    
    
    params_dict = {'product_list': ['M.3', 'M.4', 'Q.2', 'Q.3', 'Q.4'],
      'delivery_list': ['base', 'base', 'base', 'base', 'base'],
      'year_list': [2017, 2017, 2017, 2017, 2017],
      'sD': dt.datetime(2016, 1, 1, 0, 0),
      'eD': dt.datetime(2017, 2, 8, 0, 0),
      'cont': False}
    
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
       
    
    
    
    
    
    
    

        
        

