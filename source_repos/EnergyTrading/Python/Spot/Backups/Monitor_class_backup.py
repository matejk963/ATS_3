# -*- coding: utf-8 -*-
"""
Created on Sun Jan 14 10:42:29 2024

@author: krajcovic
"""
import abc

import pandas as pd
import numpy as np
from scipy.stats import kurtosis, skew
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time
from dateutil.relativedelta import relativedelta
import datetime as dt
import seaborn as sns
import os

from Loaders.DataLoader_class import DataLoader as DL
from Database.DB_reader import Database
from Loaders.EikonFut_class import EikonFut as EF
from Loaders.RLD_fetch import RLDDatabaseData

from scipy.stats import boxcox
from scipy.special import inv_boxcox

import scipy.stats as stats
from scipy.stats import t, multivariate_t


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
        
        db_reader = Database()
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
            parts.append(year_list[0])
        
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
                    spot_df = pd.concat([spot_df, aux], axis=1, join='outer')
            
                
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
    
    
    
    def __init__(self, market,  params_dict):
        super().__init__( params_dict)        
        
        
    
        
    
    
    def get_data(self):
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




class AvCapMonitor:
    def __init__(self, country='de',
                 config=r"Z:\EnergyTrading\configDB.json"):
        self._country = country
        self._sD = None
        self._eD = None
        self._db_inst = RLDDatabaseData(config)
        self._config = config
        
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
    def country_dict(self):
        my_dict = {}
        my_dict['de'] = 'DEU'
        my_dict['fr'] = 'FRA'
        my_dict['it'] = 'ITA'
        my_dict['nl'] = 'NLD'
        my_dict['be'] = 'BEL'
        my_dict['at'] = 'AUT'
        
        return my_dict
        
            
    def set_date_range(self, sD, eD):
        self._sD = sD
        self._eD = eD
        
        
    def get_data_da(self,market='de', source='local'):
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
                      sD, eD, source='local'):
        if source in ['local']:
            folder_path = r'C:\Users\krajcovic\Documents\Trading\Data\FundDatabase\AvCap'
            market_folder = self.country_dict[market]
            file_name = market.upper() + '_av_cap_' + forecast_date.strftime('%Y%m%d') + '.csv'
            file_path = os.path.join(folder_path, market_folder, file_name)
            aux = pd.read_csv(file_path, parse_dates=['datetime', 'date', 'f_date'],
                              dtype=float, index_col='datetime').drop(['date', 'f_date'],axis=1)
            aux = aux.loc[sD:eD].copy()
            return aux
                
       
            




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
        
            
    def get_raw_data(self, market='de', source='local', long=True,
                     monthly=False, monthly_parts=False,
                     normal=False, normal_parts=False, adjust_normal=True):

        if source in ['db']:
            
                    
            fct = self.dataloader_inst.get_RLD_raw_fcst(country='de').sort_values(['value_date'])
            norm = self.dataloader_inst.get_RLD_raw_normal(country='de').sort_values(['value_date'])
            norm = norm.drop_duplicates(['value_date', 'wind', 'solar', 'con'])
            df = fct.merge(norm[['value_date', 'wind', 'solar', 'con']], on='value_date', how='inner')

            return df
        elif source in ['local']:
            country = self.country_dict[market]
            if monthly:
                df = pd.DataFrame()
                for fund in ['CON', 'Wind', 'Solar']:
                    file_name = country + '_' + fund + '_00_monthly.csv'
                    folder_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Monthly_forecast'
                    file_path = os.path.join(folder_path, file_name)
                    aux = pd.read_csv(file_path,
                                         parse_dates=['forecast_date', 'value_date'])
                    
                    if df.empty:
                        df = aux.copy()
                    else:
                        df = df.merge(aux, on=['forecast_date', 'value_date'],how='inner')
                df['rld'] = df['CON'] - df['Wind'] - df['Solar']
                if monthly_parts:
                    return df[['forecast_date', 'value_date',
                               'CON', 'Wind', 'Solar']]
                else:
                    df = df[['forecast_date', 'value_date', 'rld']].copy()
                    return df
            elif normal:
                df = pd.DataFrame()
                for fund in ['CON', 'Wind', 'Solar']:
                    file_name = country + '_' + fund + '_norm.csv'
                    folder_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Normals\Normals'
                    file_path = os.path.join(folder_path, file_name)
                    aux = pd.read_csv(file_path,
                                         parse_dates=['datetime'])
                    aux.columns = ['value_date', fund]
                    aux = aux.loc[~aux['value_date'].duplicated()].copy()
                    if df.empty:
                        df = aux.copy()
                    else:
                        df = df.merge(aux, on=['value_date'],how='inner')
                df['rld'] = df['CON'] - df['Wind'] - df['Solar']
                if normal_parts:
                    return df[['value_date', 'CON', 'Wind', 'Solar']]
                else:
                    df = df[['value_date', 'rld']].copy()
                    return df
            else:
                if long:
                    file_name = country + '_ResidualDemand_00_long.csv'
                else:
                    file_name = country + '_ResidualDemand_00.csv'
                folder_path = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\RLD'
                file_path = os.path.join(folder_path, file_name)
                df = pd.read_csv(file_path,
                                     parse_dates=['forecast_date', 'value_date'])
                df = df[['forecast_date', 'value_date', 'rld']].copy()
                return df
            
        else:
            fct = self._db_inst.history_live_merge(from_=self.sD,
                                                  to_=self.eD)
            norm = self.dataloader_inst.get_RLD_raw_normal(country='de').sort_values(['value_date'])
            norm = norm.drop_duplicates(['value_date', 'wind', 'solar', 'con'])
            df = fct.merge(norm[['value_date', 'wind', 'solar', 'con']], on='value_date', how='inner')
            return df
        
    def get_raw_data_normalized(self, market='de', source='local', long=True,
                                monthly=False, smooth=False):
        if monthly:
            data = self.get_raw_data(market=market, source=source, long=long,
                                     monthly=True)
        else:
            data = self.get_raw_data(market=market, source=source, long=long)
        norm = self.get_raw_data(market=market, source=source, long=long,
                                 normal=True)
        df = data.merge(norm.reset_index(), on='value_date', how='left',
                        suffixes=('', '_norm'))
        if not smooth:
            df['rld'] = df['rld']/df['rld_norm']
        else:
            df['weekly_avg'] = df.groupby(pd.Grouper(key='value_date', freq='W'))['rld_norm'].transform('mean')
            df['rld'] = df['rld']/df['weekly_avg']

        return df[['forecast_date', 'value_date', 'rld']]
    
    def data_matrix(self, df, fct_type=0):
        
        
        out_df = df[df['forecast_date'].dt.hour==fct_type].copy()
        out_df = out_df.loc[((out_df['forecast_date']>=self.sD)&
                             (out_df['forecast_date']<=self.eD))].copy()
        if not 'rld' in out_df.columns:            
            out_df['rld'] = out_df['con_ens'] - out_df['wind_ens'] - out_df['solar_ens']
            if ('con' and 'wind' and 'solar') in out_df.columns:
                out_df['rld_n'] = out_df['con'] - out_df['wind'] - out_df['solar']
                out_df['rld'] = out_df['rld']/out_df['rld_n']
            out_df = out_df[['forecast_date', 'value_date', 'rld']].copy()
        out_df['hours'] = ((out_df['value_date'] - out_df['forecast_date']).dt.total_seconds()/3600)+1
        out_df['rld'] = out_df['rld'].fillna(method='ffill')
        if out_df['hours'].max() <400:
            out_df = out_df.loc[((out_df['hours']>24)&
                                 (out_df['hours']<361))].copy()
        else:
            out_df = out_df.loc[((out_df['hours']>24))].copy()
        

        out_df = pd.pivot_table(data=out_df, index=['forecast_date'], columns=['hours'], values=['rld'])
        out_df = out_df.fillna(method='ffill', axis=1)
        out_df.columns = out_df.columns.droplevel(0)
        return out_df
    
    
    def compile_data(self,markets=['de', 'fr', 'be', 'nl'],
                     fut_periods=720,
                     source='local'):
        for market in markets:
            if market not in list(self.data_dict):
                self.data_dict[market] = {}
                if 'nominal' not in list(self.data_dict[market]):
                    self.data_dict[market]['nominal'] = self.get_rld_curve(market=market, source=source,
                                                        fut_periods=fut_periods)
                if 'normalized' not in list(self.data_dict[market]):
                    self.data_dict[market]['normalized'] = self.get_rld_curve(market=market, source=source,
                                                        fut_periods=fut_periods,
                                                        normalize=True)
                if 'smoothed' not in list(self.data_dict[market]):
                    self.data_dict[market]['smoothed'] = self.get_rld_curve(market=market, source=source,
                                                                            fut_periods=fut_periods,
                                                                            normalize=True,
                                                                            smooth=True)
                if 'normal' not in list(self.data_dict[market]):
                    self.data_dict[market]['normal'] = self.data_dict[market]['nominal']/\
                        self.data_dict[market]['normalized']
                if 'normal_smoothed' not in list(self.data_dict[market]):
                    self.data_dict[market]['normal_smoothed'] = self.data_dict[market]['nominal']/\
                        self.data_dict[market]['smoothed']

                    
                    
        
        
    
    def get_rld_curve(self, market='de', source='local', fut_periods=8760,
                      normalize=False, smooth=False, return_date=None):
        if normalize:
            if not smooth:
                short_fcst = self.get_raw_data_normalized(market=market, source=source)
                monthly_fcst = self.get_raw_data_normalized(market=market, source=source, monthly=True)
            else:
                short_fcst = self.get_raw_data_normalized(market=market, source=source, smooth=True)
                monthly_fcst = self.get_raw_data_normalized(market=market, source=source,
                                                            smooth=True, monthly=True)
            # Process them to matrix
            short_matrix = self.data_matrix(short_fcst)
            monthly_matrix = self.data_matrix(monthly_fcst)
            additional_columns = [col for col in monthly_matrix.columns
                                  if col not in short_matrix.columns]
            df = pd.merge(short_matrix,
                          monthly_matrix[additional_columns],
                          left_index=True,
                          right_index=True,
                          how='left')
            df = df.ffill()
            if fut_periods > df.shape[1]:
                extra_hours = fut_periods - df.shape[1]
                zeros_matrix = np.zeros((df.shape[0],extra_hours))
                zeros_matrix = 1
                new_columns = np.arange(df.columns[-1]+1,fut_periods+1)
                aux = pd.DataFrame(zeros_matrix,index=df.index,columns=new_columns)
                df = pd.concat([df, aux], axis=1)
                df = df.fillna(1)
            else:
                df = df.iloc[:,:int(df.columns[-1]-1)].copy()
                df = df.fillna(1)
        
        else:            
            # First fetch the raw data for short term and monthly forecast
            short_fcst = self.get_raw_data(market=market, source=source)
            monthly_fcst = self.get_raw_data(market=market, source=source, monthly=True)
            normal_curve = self.get_raw_data(market=market, source=source, normal=True)
            # Process them to matrix
            short_matrix = self.data_matrix(short_fcst)
            monthly_matrix = self.data_matrix(monthly_fcst)
            additional_columns = [col for col in monthly_matrix.columns
                                  if col not in short_matrix.columns]
            df = pd.merge(short_matrix,
                          monthly_matrix[additional_columns],
                          left_index=True,
                          right_index=True,
                          how='left')
            df = df.ffill()
            # Ensure the index is of datetime type
            df.index = pd.to_datetime(df.index)
            
            first_col, last_col = df.columns[0], df.columns[-1]
            
            if last_col>=fut_periods:
                df = df.iloc[:,:int(last_col-1)].copy()
            else:
                extra_hours = fut_periods - df.shape[1]
                zeros_matrix = np.zeros((df.shape[0],int(extra_hours)))
                zeros_matrix = np.nan
                new_columns = np.arange(df.columns[-1]+1,fut_periods+1)
                aux = pd.DataFrame(zeros_matrix,index=df.index,columns=new_columns)
                df = pd.concat([df, aux], axis=1)
            
            # Step 1: Create a DataFrame of computed datetimes
            # Use np.tile to repeat the index for each column, and np.add.outer to add hours to these dates
            hours = np.array(df.columns.astype(int))  # Ensure the columns are integer type
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
            
        if return_date is None:
            return df
        else:
            return df.loc[return_date]
        
        
        
    """
    Here the goal is to get scenarios of the residual loads
    """
    
    
    def rld_chng_mask(self, df, df_act, mask_type, market,
                      percentile_fix=500, quantiles=3,
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
        
        def compute_quantiles_optimized(series, initial_fixed, quantiles, step=30):
            
            # Pre-compute and store relevant quantiles to avoid recalculating them
            global_deciles = np.quantile(series[:initial_fixed].dropna(), np.linspace(0, 1, quantiles + 1))
            
            # Initialize the output array
            deciles = np.full(len(series), np.nan)  # Use np.full for initialization with NaN
            
            # Apply initial fixed deciles
            for i in range(1, len(global_deciles)):
                deciles[:initial_fixed] = np.where(series[:initial_fixed] <= global_deciles[i], i - 1, deciles[:initial_fixed])
            
            # Use pandas cut function to bin data, which can be significantly faster
            # for the windows after the initial fixed part
            for start in range(initial_fixed, len(series), step):
                end = start + step
                window_series = series[start:end].dropna()
                if not window_series.empty:
                    window_deciles = np.quantile(window_series, np.linspace(0, 1, quantiles + 1))
                    # Bin data in one step per window
                    binned_data = pd.cut(window_series, bins=window_deciles, labels=False, include_lowest=True)
                    deciles[start:start+len(binned_data)] = binned_data.values
            
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
            elif mask_type in ['weekday']:
                df_weekday = df_transformed.apply(lambda x: x.dt.weekday)
                df_weekday = pd.DataFrame(np.where((df_weekday<5),1,0),
                                       columns=df_weekday.columns,
                                       index=df_weekday.index)
                # df_weekday = np.where(df_weekday<5,1,0)
                self.mask_dict[market][mask_type] = df_weekday
            elif mask_type in ['hour']:
                df_hour = df_transformed.apply(lambda x: x.dt.hour)
                df_hour = pd.DataFrame(np.where(((df_hour>7)&(df_hour<20)),1,0),
                                       columns=df_hour.columns,
                                       index=df_hour.index)
                self.mask_dict[market][mask_type] = df_hour
        else:
            if mask_type in ['value_position']:
                
                # Apply the function to your column
                initial_fixed = percentile_fix  # Set this to your fixed initial range (e.g., 200)
                # deciles_arr = [compute_quantiles(df[a], initial_fixed, quantiles) for a in df.columns if a.isnan().all()]
                # quantiles_arr = [pd.Series([np.nan] * len(df_act) if df_act[a].isna().all()
                #                             else compute_quantiles(df_act[a], initial_fixed, 10))
                #                   for a in df_act.columns]
                quantiles_arr = [pd.Series([np.nan] * len(df_act) if df_act[a].isna().all()
                                            else calculate_quantiles_vectorized(df_act[a],
                                                                                  percentile_fix, 10))
                                  for a in df_act.columns]
                # quantiles_arr = [compute_quantiles_optimized(df_act[a], initial_fixed, 10)
                #                  for a in df_act.columns if not df_act[a].isna().all()]
                quantiles_df = pd.DataFrame(np.array(quantiles_arr).T,
                                       columns=[a for a in df_act.columns],
                                       index=df_act.index)
                self.mask_dict[market][mask_type] = quantiles_df
                
            elif mask_type in ['hist_position']:
                data_da = self.get_da_data(df_act).set_index('value_date').resample('D').mean()

                data_da['roll_mean'] = data_da['rld_da'].rolling(window=14, min_periods=1).mean()
                data_da['quantiles'] = compute_quantiles(data_da['roll_mean'], percentile_fix, quantiles)
                data_da['quantiles'] = np.where(data_da['quantiles']==quantiles,quantiles-1,data_da['quantiles'])
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
            type_list = ['month', 'weekday', 'hour', 'value_position',
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

    def get_mask(self, filter_values, df, df_act, market, types='all'):
        
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

        # Initialize the result with the comparison of the first DataFrame
        if keys[0] in ['month']:
            value_from ,value_middle, value_to = get_month_spread(values[0])
            mask = (masks[keys[0]]==value_from)|(masks[keys[0]]==value_to)|(masks[keys[0]]==value_middle)
        else:
            mask = masks[keys[0]] == values[0]

        # Loop through the remaining keys and values, updating the result
        for key, value in zip(keys[1:], values[1:]):
            if key in ['month']:
                value_from, value_to = get_month_spread(value)
                mask += (masks[key]>=value_from)&(masks[key]<=value_to)
            else:
                # Start from the second item
                mask &= (masks[key] == value)
            
        return mask
    
    
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
    
        
    
    def get_curve_values(self, curve, df_act, curve_da, lookback=1000):
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
        curve_hour = curve_transformed.apply(lambda x: x.dt.hour)
        curve_hour = pd.DataFrame(np.where(((curve_hour>7)&(curve_hour<20)),1,0),
                               columns=curve_hour.columns,
                               index=curve_hour.index)
        days_forward = [(a-1)//24 for a in curve.columns]
        forward_days = pd.DataFrame(np.array([days_forward]),
                               columns=[a for a in curve.columns],
                               index=curve.index)
        
        data_da = self.get_da_data(df_act)
        data_da = data_da['rld_da'].rolling(14).mean().iloc[-lookback:].copy()
        conditions = ['month', 'weekday', 'hour', 'value_position',
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
                    quantile = find_value_quantile(val, val_ser, 5)
                    aux_val.append(quantile)
                    aux_val_names.append(mask_type)
                elif mask_type in ['hist_position']:
                    quantile = find_value_quantile(curve_da, data_da, 3)
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
                    
                
                    
    def get_scenarios(self, market, days_fwd_list, source,
                      curve_fcst_date='last',
                      scenario_list=[10,25,50,75,90]):
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
        normalized_matrix_smooth = self.data_dict[market]['smoothed']
        # Get normal data
        normal_matrix = self.data_dict[market]['normal']
        # Get changes of normlized data
        # changes_dict = self.get_hist_changes(days_fwd_list)
        changes_dict = {}
        for day in days_fwd_list:
            day_shift = day - 1
            shifted_data = normalized_matrix.shift(-day_shift).shift(day_shift*24,axis=1)
            data_chng = shifted_data-normalized_matrix
            changes_dict[day] = data_chng
            
        # Get DA timeseries of normalized value
        da_data = self.get_da_data(normalized_matrix)
        # Get curves
        if curve_fcst_date in ['last']:
            curve_date = normalized_matrix.index[-1]
        else:
            curve_date = curve_fcst_date
        nominal_curve = nominal_matrix.loc[[curve_date]].copy()
        normalized_curve = normalized_matrix.loc[[curve_date]].copy()
        normal_curve = normal_matrix.loc[[curve_date]].copy()
        
        # Get conditional values for the values in curve
        values_df = self.get_curve_values(normalized_curve, normalized_matrix,
                                           da_data.set_index('value_date').resample('D').\
                                               mean().rolling(14).mean().iloc[-1].values[0])
        
        # Get scenarios for day ahead
        # For scenario generatio there will be standalone function
        # There should be covered the cutoff date for matrix to compute the history
        scen_dict = {}
        for fwd_day in days_fwd_list:
            scen_dict[fwd_day] = self.get_scenarios_for_hour(market, fwd_day, curve_date,
                                                             normalized_curve, normal_curve,
                                                             values_df, changes_dict,
                                                             normalized_matrix,
                                                             normalized_matrix_smooth,
                                                             scenario_list)
        end_time = time.time()
        print(f"get_scenarios took {end_time - start_time} seconds to execute")
        return scen_dict
            
        
            
        
        
        
        

    
    
    def get_scenarios_for_hour(self, market, fwd_day, curve_date,
                               normalized_curve, normal_curve,
                               values_df,changes_dict,
                               normalized_matrix, normalized_matrix_smooth,
                               scenarios=[10,25,50,75,90]):
        start_time = time.time()
        # Automatically add 'real_value' index to scenario list
        scenario_list_adj = scenarios.copy()
        if 'rld' not in scenario_list_adj:
            scenario_list_adj.append('rld')
        if 'mean' not in scenario_list_adj:
            scenario_list_adj.append('mean')
        # Get matrix of changes for given fwd_day
        change_matrix = changes_dict[fwd_day]
        # Adjust the matrix of values (matrix) and matrix of changes for curve date
        # Cut the matrices in date of curve to secure objective analysis of history for the given curve date
        normalized_matrix_adj = normalized_matrix.loc[:curve_date].iloc[:-1].copy()
        normalized_matrix_smooth_adj = normalized_matrix_smooth.loc[:curve_date].iloc[:-1].copy()
        change_matrix_adj = change_matrix.loc[:curve_date].iloc[:-1].copy()
        # Adjust the value_ser for fwd_day shift (fwd_day*24)
        shift_factor = ((fwd_day)*24)+1
        values_df_adj = values_df.loc[:,shift_factor:].copy()
        normalized_curve_adj = normalized_curve.loc[:,shift_factor:].copy()
        normal_curve_adj = normal_curve.loc[:, shift_factor:].copy()
        # Create empty scenario df for appending scenario percentiles
        scen_df = pd.DataFrame(index=scenario_list_adj)
        # Loop through hours of value_series and get scenario distribution
        # and subsequent percentiles
        emp_dist_list = []
        dist_params_list = []
        for i, hour in enumerate(values_df_adj.columns):
            percentiles_list = []
            scenario_list = []
            curve_value = normalized_curve_adj[hour].iloc[0]
            values = values_df_adj[hour].to_list()
            mask = self.get_mask(values,change_matrix_adj, normalized_matrix_smooth_adj, market)
            aux = change_matrix_adj[mask].copy()
            non_nan_mask = ~aux.isna()
            non_nan_values = aux[non_nan_mask].values.flatten()
            non_nan_values = non_nan_values[~np.isnan(non_nan_values)]
            emp_dist_list.append(non_nan_values+curve_value)
            dist_data = non_nan_values+curve_value
            if len(non_nan_values)==0:
                print('1595')
            dist_params_list.append(self.estimate_best_fit_distribution(non_nan_values))
            if ~non_nan_values.any():
                print('stop')
            for perc in [10,25,50,75,90]:
                percentile = np.percentile(non_nan_values, perc)
                scenario_list.append(curve_value+percentile)
                # percentiles_list.append(percentile)
            scenario_list.append(curve_value)  
            scenario_list.append(np.nanmean(non_nan_values)+curve_value)
            
            # if len(scen_df.index) == 7:
            #     print('stop')
            scen_df[hour] = scenario_list
            
        # Get df of actual senarios in nominal (GW) values
        scen_df_act = scen_df*pd.DataFrame([normal_curve_adj.values[0]
                                              for a in range(len(scen_df))],
                                              columns=scen_df.columns,
                                              index=scen_df.index) 
        scen_df_act = scen_df_act.T
        scen_df_act.index = normalized_curve.index[0] + pd.to_timedelta(scen_df_act.index-1,unit='h')
        scen_df_out = scen_df.T
        scen_df_out.index = scen_df_act.index
        end_time = time.time()
        print(f"get_scenarios_for_hour took {end_time - start_time} seconds to execute")
        return scen_df_act, scen_df_out, emp_dist_list, dist_params_list, curve_value
        # return dist_params_list
    
    
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
                            
            
    
    def get_hist_changes(self, days_fwd_list, market='de', source='local'):
        # Fetch normalized data fro up to month ahead forecast
        data = self.get_rld_curve(market=market, source=source,
                                  normalize=True)
        development_days = data.shape[1]//24
        data = data.iloc[:,:development_days*24].copy()
        # Fetch all changes of RLD
        data_chng_dict = {}
        for day in days_fwd_list:
            shifted_data = data.shift(-day).shift(day*24,axis=1)
            data_chng = shifted_data-data
            data_chng_dict[day] = data_chng
            
        # Create mask for months, weekday and hour od day
        
            
        return data_chng_dict
    
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
                      scenario_list=[10,25,50,75,90],
                      runs=200):
        
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
        
        self.compile_data()
        
        # Turn raw data to data matrix
        normalized_matrix = self.data_dict[market]['normalized']
        normalized_matrix_smooth = self.data_dict[market]['smoothed']
        normal_matrix = self.data_dict[market]['normal']
        normal_matrix_smooth = self.data_dict[market]['normal_smoothed']
        nominal_matrix = self.data_dict[market]['nominal']
        
        data_da = self.get_da_data(normalized_matrix)
        # Get curves
        if curve_fcst_date in ['last']:
            curve_date = normalized_matrix.index[-1]
        else:
            curve_date = curve_fcst_date
            
        normalized_matrix_adj = normalized_matrix.loc[:curve_date].iloc[:-1].copy()
        normalized_matrix_smooth_adj = normalized_matrix_smooth.loc[:curve_date].iloc[:-1].copy()
        
        if market not in list(self.mask_dict):
            self.mask_dict[market] = {}
        if 'value_position' not in list(self.mask_dict[market]):
            self.rld_chng_mask(normalized_matrix_smooth_adj, normalized_matrix_smooth_adj, 'value_position', market)
            
        quantiles = self.mask_dict[market]['value_position'].copy()
        days_change = quantiles.shape[1]//24
       
        transition_matrix = self.calculate_transition_matrix(self.get_da_data(quantiles), 10)
        
        scen_dict = self.get_scenarios(market=market,
                                            days_fwd_list=days_fwd_list,
                                            curve_fcst_date=curve_fcst_date,
                                            source=source)
        
        
        
        quantile_edge = self.get_quantile_edges(normalized_matrix_smooth_adj, 10)
        adjusted_quantile_edges = np.concatenate(([-np.inf], quantile_edge[1:-1], [np.inf]))
        
        normal_curve = normal_matrix.loc[curve_date].copy()
        normal_curve_smooth = normal_matrix_smooth.loc[curve_date].copy()
        nominal_curve = nominal_matrix.loc[curve_date].copy()
        
        quantile_samples_dict = {}
        for fwd_day in days_fwd_list:
            de_scen_normalized = scen_dict[fwd_day][1]
            hours_index = (de_scen_normalized.index[:-1] - curve_date).total_seconds()/3600
            mcmc_scenarios = []
            
            
            base_state_list = []
            start_time1 = time.time()
            for i, hour in enumerate(hours_index):
                
                normal_value = normal_curve[hour]
                normal_value_smooth = normal_curve_smooth[hour]
                nominal_value = nominal_curve[hour]
                aux_dist, aux_params = scen_dict[fwd_day][3][i]
                aux_samples = aux_dist.rvs(*aux_params[:-2],
                                            loc=aux_params[-2],
                                            scale=aux_params[-1],
                                            size=1000)
                aux_samples_nominal = aux_samples*normal_value + nominal_value
                aux_samples_smooth = aux_samples_nominal/normal_value_smooth
                
                dist_states = np.unique([self.assign_quantile(a,adjusted_quantile_edges)
                                         for a in aux_samples_smooth])
                dist_states = np.unique([a if a<10 else 9 for a in dist_states])
                
                run_list = []
                base_state_aux = []
                start_time2 = time.time()
                for run in range(runs):
                    
                    if i == 0:
                        rand_draw_nominal = np.random.choice(aux_samples_nominal)
                        rand_draw_smooth = rand_draw_nominal/normal_value_smooth
                        run_list.append(rand_draw_nominal)
                        base_state = self.assign_quantile(rand_draw_smooth, adjusted_quantile_edges)
                        base_state_aux.append(base_state)
                    else:
                                                
                        base_state = base_state_list[i-1][run]

                        selected_states = transition_matrix[base_state][dist_states]
                        
                        if not bool(set(np.nonzero(transition_matrix[base_state])[0])&
                                set(dist_states)):
                            if base_state < dist_states.min():
                                next_state = dist_states.min()
                            else:
                                next_state = dist_states.max()
                        else:
                            transition_probabilities = selected_states/np.sum(selected_states)
                            quantile_samples = np.random.choice(dist_states,
                                                                size=200,
                                                                p=transition_probabilities)
                            next_state = np.random.choice(quantile_samples)                             
                        
                        intervals = self.select_interval(next_state,adjusted_quantile_edges)
                        intervals_nominal = [a*normal_value_smooth for a in intervals]
                        intervals_nominal_diff = intervals_nominal-nominal_value
                        intervals_adj = tuple(intervals_nominal_diff/abs(normal_value))
                        aux_samples_adj = self.sample_from_truncated_distribution(dist_type=aux_dist,
                                                                                  dist_params=aux_params,
                                                                                  interval=intervals_adj,
                                                                                  num_samples=runs)
                        aux_samples_adj_nominal = aux_samples_adj*abs(normal_value) + nominal_value
                        run_list.append(np.random.choice(aux_samples_adj_nominal))
                        base_state_aux.append(next_state)
                end_time2 = time.time()
                base_state_list.append(base_state_aux)
                mcmc_scenarios.append(run_list)
            end_time1 = time.time()
            print(f"run loop in get_timeseries_scenarios \
                  took {end_time1 - start_time1} seconds to execute")
            print(f"hour loop in get_timeseries_scenarios \
                  took {end_time1 - start_time1} seconds to execute")

            
        # Scenarios generation with
        
        scenarios_df = pd.DataFrame(np.array(mcmc_scenarios),
                                    index=scen_dict[fwd_day][0].index[:-1])
        end_time = time.time()
        print(f"get_timeseries_scenarios took {end_time - start_time} seconds to execute")
        return scenarios_df    
    
    def simulate_multiple_scenarios(self, markets=['de', 'fr', 'be', 'nl'],
                                    days_fwd_list=[2,5,10], curve_fcst_date='last', percentile_fix=500,
                                    scenario_list=[10,25,50,75,90],
                                    runs=1000, source='local', degrees_of_freedom=10):
        def covariance_to_correlation(covariance_matrix):
            std_dev = np.sqrt(np.diag(covariance_matrix))
            correlation_matrix = covariance_matrix / np.outer(std_dev, std_dev)
            return correlation_matrix
        self.compile_data()
        # Get toghether day ahead data
        da_data = pd.DataFrame()
        for market in markets:
            aux_matrix = self.data_dict[market]['normalized']
            aux_da = self.get_da_data(aux_matrix).set_index('value_date').iloc[-2200:]
            if da_data.empty:
                da_data = aux_da.copy()
            else:
                da_data = pd.concat([da_data, aux_da], axis=1, join='inner')
        
        # Estimate covariance
        cov_matrix = da_data.cov().values
        correlation_matrix = covariance_to_correlation(cov_matrix)
        
        # Estimate and sample copula
        uniform_samples = self.sample_uniform_from_copula(1000, da_data.shape[1],
                                                          degrees_of_freedom,
                                                          correlation_matrix)
            
        
        scen_dict = {}
        for fwd_day in days_fwd_list:
            # Generate scenarios for each market
            scen_dict[fwd_day] = {}
            for market_index, market in enumerate(markets):
                single_scen = self.get_timeseries_scenarios(market, days_fwd_list, source='local',
                                                            curve_fcst_date=curve_fcst_date)
                samples = []
                index_list = []
                for i, row in single_scen.iterrows():
                    dist_object = self.estimate_best_fit_distribution(row.values)
                    market_uniform_samples = uniform_samples[:, market_index]
                    market_samples = self.sample_from_marginal(market_uniform_samples, dist_object)
                    samples.append(market_samples)
                    index_list.append(i)
                    
                scen_dict[fwd_day][market] = samples, index_list
                
        return scen_dict
                    
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
        
# if __name__ == '__main__':
    
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
       
    
    
    
    
    
    
    

        
        

