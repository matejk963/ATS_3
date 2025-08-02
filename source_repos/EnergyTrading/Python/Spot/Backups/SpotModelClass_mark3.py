596371# -*- coding: utf-8 -*-
"""
Created on Wed Dec 27 13:25:36 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import datetime as dt
from dateutil.relativedelta import relativedelta
import os
import re
import copy
from collections import defaultdict
import time
from joblib import Parallel, delayed
from scipy.optimize import OptimizeWarning
import warnings
from itertools import combinations
import holidays
from itertools import product

from Utilities.date_functions import start_date, end_date

from Database.GenFetchClass import ENTSOEData as EED
from Loaders.loader import spot_loader as SL

from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import AvCapMonitor as AM
from Spot.Monitor_class import FuturesMonitor as FM
from Spot.Monitor_class import SettleMonitor as SM

from Loaders.EikonFut_class import EikonFut as EF
import refinitiv.data as rd
from Database.TPData import TPDataAssembly as TDA

from sklearn.preprocessing import StandardScaler, PowerTransformer
from xgboost import XGBRegressor
from sklearn.linear_model import LinearRegression
import xgboost as xgb
from sklearn.ensemble import ExtraTreesRegressor

class PowerModel:
    
    """
    Class should capture general dynamics of modeling power price:
        Data => Model => Forecast:
            Data: Raw => Processing => Scaling => Data
            Model: Model type => Model parameters => Fitting => Forecast
            Forecast: Forecasted data => Processing => Analysys/Strategies
        
    Data for power price modeling:
        RLD
        Fuel prices
        Available capacities
    
    Structue of data depends on train and test part.
    Train data should be DA data of past period X hours (depending on model)
    Test data will generaly be a future curve in hourly resolution that represents desired futures products.
    Test data may be in form of multiple scenarios of futures curve
    
    Models used are XGBoost, ExtraTrees Regressor and Linear Regression
    Ensemble model will be enabled
    
    Classes for data fetch:
        RLD - RldMonitor
        FuelsData - FuturesMonitor
        AvCap - AvCapMonitor (yet to be build)
        
    Primary forecasted value will be Gas Heat Rate (ghr) computed as:
        ghr = power price/(gas price + 0.2*eua price)
    Class will handle conversion to price
    
    
    
    """
    
    def __init__(self, params_dict):
        self._params_dict = params_dict.copy()
        self._original_params_dict = copy.deepcopy(params_dict)
        self._rm_inst = None
        self._am_inst = None
        self._pivot_date = pd.to_datetime(dt.datetime.now().date())
        self._models_inst = {}
        self._scalers_inst = {}
        self.raw_data = {}

        

    
    @property
    def params_dict(self):
        return self._params_dict
    @property
    def original_params_dict(self):
        return self._original_params_dict
    
    
    @property
    def models_inst(self):
        return self._models_inst
    
    @property
    def scalers_inst(self):
        return self._scalers_inst
    
    @property
    def rm_inst(self):
        if self._rm_inst is None:
            self._rm_inst = RM()
            self._rm_inst.set_date_range(self.sD, self.eD)
        return self._rm_inst
    @property
    def am_inst(self):
        if self._am_inst is None:
            self._am_inst = AM()
            self._am_inst.set_date_range(self.sD, self.eD)
        return self._am_inst
    
    
    
    @property
    def sD(self):
        if not hasattr(self, '_sD'):
            self.set_date_range()
        return self._sD
    
    @property
    def eD(self):
        if not hasattr(self, '_eD'):
            self.set_date_range()
        return self._eD
    
    @property
    def pivot_date(self):
        return self._pivot_date
    
    def update_params_dict(self, new_params_dict):
        self._params_dict = new_params_dict
    
    def set_pivot_date(self, new_pivot_date):
        self._pivot_date = new_pivot_date
    
    def set_date_range(self):
        self._sD = self.params_dict['sD']
        self._eD = self.params_dict['eD']
        
    @staticmethod
    def get_start_date_from_week(year, week_number):
        # Create a date object for January 1st of the given year
        jan_1 = datetime(year, 1, 1)
        # Calculate the number of days to the first Monday of the year
        days_to_monday = (7 - jan_1.weekday()) % 7  # 0 represents Monday
        # Calculate the start of the week in ISO terms (adjust to the first Monday)
        start_of_iso_week = jan_1 + timedelta(days=days_to_monday)
        # Calculate the start date of the given week number, subtract 1 from week_number because timedelta weeks starts from 0
        start_date_of_week = start_of_iso_week + timedelta(weeks=week_number - 1)
        # Return the start date as a datetime object (no need to convert to pandas datetime unless specifically needed)
        return start_date_of_week
   
    
    @staticmethod
    def get_nearest_older_business_day(date):
        # Subtract a day at a time until you get a weekday
        while date.weekday() >= 5:  # 5 for Saturday, 6 for Sunday
            date -= timedelta(days=1)
        return date
    
    def get_curve_start_end_date(self):
        self.curve_start_date = self.pivot_date
        self.curve_end_date = None
        for product, delivery, year in zip(self.params_dict['product_list'],
                                           self.params_dict['delivery_list'],
                                           self.params_dict['year_list']):
            aux_start, aux_end = self.get_start_end_product_date(product,
                                                                 delivery,
                                                                 year)
            # if self.curve_start_date is None:
            #     self.curve_start_date = aux_start
            # else:
            #     if self.curve_start_date > aux_start:
            #         self.curve_start_date = aux_start
            if self.curve_end_date is None:
                self.curve_end_date = aux_end
            else:
                if self.curve_end_date < aux_end:
                    self.curve_end_date = aux_end
                
    

    def get_start_end_product_date(self, product,delivery,
                                   year):
        if '.' in product:
            period, tenor = product.split('.')
            tenor = int(tenor)
            if period in ['m', 'M']:
                del_start = dt.datetime(int(year),int(tenor),1)
                del_end = del_start + relativedelta(months=1) - dt.timedelta(hours=1)
            elif period in ['q', 'Q']:
                del_start = dt.datetime(int(year),int(tenor)*3-2,1)
                del_end = del_start + relativedelta(months=3) - dt.timedelta(hours=1)
            elif period in ['y', 'Y']:
                del_start = dt.datetime(int(year),1,1)
                del_end = del_start + relativedelta(months=12) - dt.timedelta(hours=1)
            elif period.lower() in ['w', 'wk']:
                del_start = self.get_start_date_from_week(year, tenor)
                del_end = del_start + dt.timedelta(days=7) - dt.timedelta(hours=1)
            elif period.lower() in ['wknd']:
                del_start = self.get_start_date_from_week(year, tenor) + dt.timedelta(days=5)
                del_end = del_start + dt.timedelta(days=8) - dt.timedelta(hours=1)
            elif period.lower() in ['d', 'da']:
                del_start = dt.datetime(year,1,1) + pd.timedelta(days=tenor)
                del_end = del_start + pd.timedelta(days=1)
        else:
            del_start = start_date(self.pivot_date,product)
            del_end = end_date(self.pivot_date, product)
        # if delivery in ['peak']:
        #     del_end = self.get_nearest_older_business_day(del_end)
        return del_start, del_end
            
        
    
    def get_futures_periods(self):
        fut_periods_list = []
        for product, delivery, year in zip(self.params_dict['product_list'],
                                           self.params_dict['delivery_list'],
                                           self.params_dict['year_list']):
            del_start, del_end = self.get_start_end_product_date(product, delivery, year)

            fut_periods_list.append((del_end - self.pivot_date).total_seconds()//3600 + 1)
            
        return max(fut_periods_list)

            
            
        
        
        
    
    def get_rld_data(self, source='db', normal_correction_factor=10):
        """
        Function for retrieving both day ahead and futures curve data
        
        Future periods are given by params dict as neccesary for the last period desired

        Returns
        -------
        None.

        """
        markets = [a for a in np.unique(self.params_dict['market_list'])
                   if a.lower() not in ['gas', 'coal', 'eua', 'ttf', 'the']]
        markets = ['de', 'fr', 'be', 'nl', 'at']
        fut_periods = self.get_futures_periods()
        
        for market in markets:
            if not market in list(self.raw_data):
                self.raw_data[market] = {}
            if not 'rld_data' in list(self.raw_data[market]):
                self.raw_data[market]['rld_data'] = {}
            
            if not 'nominal_matrix' in list(self.raw_data[market]['rld_data']):
                # if 'nominal_matrix' not in list(self.rld_data_dict[market]):
                self.raw_data[market]['rld_data']['nominal_matrix'] = self.rm_inst.get_fund_curve('ResidualDemand', 
                                                                                  '00', normalize_to=None,
                                                                                  market=market, source=source,
                                                                                  fut_periods=fut_periods)
            if not 'rld_da' in list(self.raw_data[market]['rld_data']):
                # if 'da_data' not in list(self.rld_data_dict[market]):
                self.raw_data[market]['rld_data']['rld_da'] = self.rm_inst.get_da_data(self.raw_data[market]['rld_data']['nominal_matrix'])
                
    def get_hydro_data(self, source='db'):
        markets = [ 'fr', 'at']
        fut_periods = self.get_futures_periods()
        
        for market in markets:
            if not 'hydro_data_dict' in list(self.raw_data[market]):
                self.raw_data[market]['hydro_data_dict'] = {}
            if not 'nominal_matrix' in list(self.raw_data[market]['hydro_data_dict']):
                # if 'nominal_matrix' not in list(self.rld_data_dict[market]):
                self.raw_data[market]['hydro_data_dict']['nominal_matrix'] = self.rm_inst.get_fund_curve('INF', 
                                                                                  '00', normalize_to=None,
                                                                                  market=market, source=source,
                                                                                  fut_periods=fut_periods)
            if not 'hydro_da' in list(self.raw_data[market]['hydro_data_dict']):
                # if 'da_data' not in list(self.rld_data_dict[market]):
                self.raw_data[market]['hydro_data_dict']['hydro_da'] = self.rm_inst.get_da_data(self.raw_data[market]['hydro_data_dict']['nominal_matrix'])
                    
    def get_rld_normal(self, source='local'):
        markets = [a for a in np.unique(self.params_dict['market_list'])
                   if a.lower() not in ['gas', 'coal', 'eua', 'ttf', 'the']]
        markets = ['de', 'fr', 'be', 'nl']
        if not hasattr(self,'rld_data_dict'):
            self.rld_data_dict = {}
        for market in markets:
            if not market in list(self.rld_data_dict):
                self.rld_data_dict[market] = {}
            if 'normal' not in list(self.rld_data_dict[market]):
                self.rld_data_dict[market]['normal'] = self.rm_inst.get_fund_data('normal',
                                                                                 'ResidualDemand', 
                                                                                  '00', 
                                                                                  market=market, 
                                                                                  source=source).set_index('value_date')
                    
    def get_av_cap_da(self, markets=['de', 'fr'], source='db'):
        av_cap = pd.DataFrame()
        for market in markets:

            if not 'av_cap_da' in list(self.raw_data[market]):
                self.raw_data[market]['av_cap_da'] = self.am_inst.get_data_da(market=market, source=source)
    
    def get_av_cap_fcst(self, markets=['de', 'fr'], source='db'):
        
        if hasattr(self, 'av_cap_for_fcst_dict'):
            for market in markets:
                if not market in list(self.av_cap_for_fcst_dict):
                    self.av_cap_for_fcst_dict[market] = self.am_inst.get_data_fcst_raw(market,source)
        elif not hasattr(self, 'av_cap_for_fcst_dict'):
            self.av_cap_for_fcst_dict = {}
            for market in markets:
                self.av_cap_for_fcst_dict[market] = self.am_inst.get_data_fcst_raw(market,source)
        

        forecast_date = self.pivot_date
       
        self.get_curve_start_end_date()
        del_start, del_end = self.curve_start_date, self.curve_end_date

        for market in markets:
            if not market in list(self.raw_data):
                self.raw_data[market] = {}
            aux = self.av_cap_for_fcst_dict[market].copy()
            aux = aux.loc[aux['forecast_date'].dt.date==forecast_date.date()].copy()
            aux.set_index('value_date', inplace=True)
            aux = aux.sort_values(by=['value_date', 'forecast_date'])                
            aux = aux[~aux.index.duplicated(keep='last')]
            
            
            aux = aux.resample('min').ffill()
            
            try:
                aux.reset_index(inplace=True)
            except:
                print('316')
            
            aux.set_index('value_date',inplace=True)
            aux = aux.resample('h').mean()
            aux.reset_index(inplace=True)
            aux = aux.loc[((aux['value_date']>=del_start)&
                           (aux['value_date']<
                            (pd.to_datetime(del_end.date())
                             +dt.timedelta(days=1))))].copy()
            aux = aux.drop(['forecast_date'],axis=1)
            aux.set_index('value_date', inplace=True)
            # aux.columns = [a + '_' + market for a in aux.columns]
            self.raw_data[market]['av_cap_fcst'] = aux.copy()
            
        
                
    
    def create_fuels_data_dict(self, gas_list,
                               coal_list, eua_list):
        if not hasattr(self, 'curve_start_date'):
            self.get_curve_start_end_date()
        aux_range = list(pd.date_range(start=self.curve_start_date,
                                  end=self.curve_end_date,freq='MS'))
        front_month_date = (self.curve_start_date + relativedelta(months=1)).replace(day=1)
        
        aux_range.append(front_month_date)
        aux_range = np.unique(aux_range)
        
        product_list_months = ['M.' + str(a.month) for a in aux_range]
        prod_list_len = len(product_list_months)
        year_list = [a.year for a in aux_range]
        

        fuels_params_dict = {}
        
        fuels_params_dict['market_list'] = ['gas', 'coal', 'eua'] * prod_list_len
        fuels_params_dict['market_list'].sort()
        fuels_params_dict['product_list'] = product_list_months * 3
        fuels_params_dict['delivery_list'] = ['base'] * prod_list_len * 3
        # fuels_params_dict['delivery_list'] = [a if a =='base' else 'base' for a in 
        #                                       self.params_dict['delivery_list']] * 3
        fuels_params_dict['year_list'] = year_list * 3
        fuels_params_dict['sD'] = self.params_dict['sD']
        fuels_params_dict['eD'] = self.params_dict['eD']
        fuels_params_dict['nl'] = self.params_dict['ns']
        fuels_params_dict['cont'] = False
        return self.drop_duplicates_from_fuels_dict(fuels_params_dict)
    
    @staticmethod
    def drop_duplicates_from_multiple_lists(product_list, delivery_list, year_list):
        list1 = product_list
        list2 = delivery_list
        list3 = year_list
        
        
        # Combine the lists into a list of tuples
        combined = list(zip(list1, list2, list3))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_combined = [x for x in combined if x not in seen and not seen.add(x)]
        
        # Unzip the list of tuples back into separate lists
        unique_list1, unique_list2, unique_list3 = zip(*unique_combined)
        
        # If you need them to be lists instead of tuples, convert them
        unique_list1, unique_list2, unique_list3 = list(unique_list1), list(unique_list2), list(unique_list3)
        
        return unique_list1, unique_list2, unique_list3

    
    @staticmethod
    def drop_duplicates_from_fuels_dict(fuels_params_dict):
        list1 = fuels_params_dict['market_list']
        list2 = fuels_params_dict['product_list']
        list3 = fuels_params_dict['delivery_list']
        list4 = fuels_params_dict['year_list']
        
        # Combine the lists into a list of tuples
        combined = list(zip(list1, list2, list3, list4))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_combined = [x for x in combined if x not in seen and not seen.add(x)]
        
        # Unzip the list of tuples back into separate lists
        unique_list1, unique_list2, unique_list3, unique_list4 = zip(*unique_combined)
        
        # If you need them to be lists instead of tuples, convert them
        unique_list1, unique_list2, unique_list3, unique_list4 = list(unique_list1), list(unique_list2), list(unique_list3), list(unique_list4)
        
        fuels_params_dict['market_list'] = unique_list1
        fuels_params_dict['product_list'] = unique_list2
        fuels_params_dict['delivery_list'] = unique_list3
        fuels_params_dict['year_list'] = unique_list4
        return fuels_params_dict
    
    def create_fuels_curve(self):
        spot_prices = self.raw_data['fuels_da'].loc[[self.pivot_date]].copy()
        df = self.raw_data['fuels_fut'].copy()
        
        # Extract unique months and years from the column names
        # Extract unique months and years from the column names
        columns = df.columns
        months = sorted(set('_'.join(col.split('_')[1:3]) for col in columns))
        
        dates = [pd.to_datetime(f"{m.split('_')[1]}-{m.split('_')[0].split('.')[1]}-01") for m in months]
        # Determine the start and end date
        start_date = min(dates)
        end_date = (max(dates) + pd.offsets.MonthEnd(1)).replace(hour=23)
        
        # Create an hourly date range
        hourly_index = pd.date_range(start=start_date, end=end_date, freq='h')
        
        # Initialize the new DataFrame with hourly index
        hourly_df = pd.DataFrame(index=hourly_index)
        
        # Get coal OLS coefficients
        aux_df = df.loc[:self.pivot_date].iloc[-30:].copy()
        self.gas_coal_coefs = {}
        for month in months:
            coal_name = f"coal_{month.split('_')[0]}_{month.split('_')[1]}_base"
            gas_name = f"gas_{month.split('_')[0]}_{month.split('_')[1]}_base"
            coefs = np.polyfit(aux_df[gas_name].values,aux_df[coal_name].values, deg=1)
            self.gas_coal_coefs[month] = coefs
        
        
        
        # Populate the new DataFrame with the monthly values
        for month in months:
            aux_month, aux_year = month.split('_')
            aux_month = aux_month.split('.')[1]
            month_start = pd.to_datetime(f"{aux_year}-{aux_month.zfill(2)}-01")
            month_end = (month_start + pd.offsets.MonthEnd(1)).replace(hour=23)
            mask = (hourly_df.index >= month_start) & (hourly_df.index <= month_end)
            for product in ['coal', 'eua', 'gas']:
                col_name = f"{product}_{month.split('_')[0]}_{month.split('_')[1]}_base"
                hourly_df.loc[mask, product] = df.loc[self.pivot_date, col_name]
        hourly_df = hourly_df.rename(columns={'coal': 'spot_coal',
                                              'gas': 'ttf_da'})
        hourly_df = pd.concat([hourly_df,spot_prices]).sort_index()
        # Create a complete date range with hourly frequency
        complete_date_range = pd.date_range(start=hourly_df.index.min(), end=hourly_df.index.max(), freq='h')
        hourly_df = hourly_df[~hourly_df.index.duplicated(keep='first')].copy()
        # Reindex the DataFrame to include all hours
        hourly_df = hourly_df.reindex(complete_date_range)
        
        # Perform linear interpolation to fill missing values
        hourly_df.interpolate(method='linear', inplace=True)
        return hourly_df
        
    def get_fuels_data(self):
        
        no_of_products = len(self.params_dict['product_list'])
        gas_list = ['gas'] * no_of_products
        coal_list = ['coal'] * no_of_products
        eua_list = ['eua'] * no_of_products
        fuels_params_dict = self.create_fuels_data_dict(gas_list, coal_list, eua_list)

        if not 'fuels_fut' in list(self.raw_data):
            fm_inst = FM(fuels_params_dict)
            self.raw_data['fuels_fut'] = fm_inst.get_data(reference_date=self.pivot_date)
        elif not self.pivot_date in self.raw_data['fuels_fut'].index:
            fm_inst = FM(fuels_params_dict)
            self.raw_data['fuels_fut'] = fm_inst.get_data(reference_date=self.pivot_date)
        if not 'fuels_da' in list(self.raw_data):
            sm_inst = SM(fuels_params_dict)
            self.raw_data['fuels_da'] = sm_inst.get_spot_data_raw().ffill()             
        

            
        
        
    
    def get_power_data(self):
        # if not hasattr(self, 'power_fut'):
        #     fm_inst = FM(self.params_dict)
        #     self.power_fut = fm_inst.get_data()
        if not 'power_da' in list(self.raw_data):
            sm_inst = SM(self.params_dict)
            self.raw_data['power_da'] = sm_inst.get_spot_data_raw()
    
    def assemble_raw_data(self, source='db'):
        if not hasattr(self, 'raw_data'):
            self.raw_data = {}
        self.get_rld_data()
        self.get_hydro_data()
        self.get_power_data()
        self.get_fuels_data()
        self.get_av_cap_da()
        av_cap_market_list = []
        for market, market_dict in self.raw_data.items():
            if market in ['fuels_da', 'fuels_fut', 'power_da']:
                continue
            else:
                if 'av_cap_fcst' in list(market_dict):
                    del self.raw_data[market]['av_cap_fcst']
                    av_cap_market_list.append(market)
                else:
                    continue
        self.get_av_cap_fcst()
    
    def assemble_da_data(self, source='db'):
        
        markets = [a for a in list(self.raw_data) if a not in ['power_da', 'fuels_da',
                                                               'fuels_fut']]
        
        power_da = self.raw_data['power_da']
        fuels_da = self.raw_data['fuels_da']
        da_data = power_da.merge(fuels_da,left_index=True,
                                      right_index=True, how='left')
        av_cap_columns = []
        for market in markets:
            
            if 'rld_data' in self.raw_data[market]:
                aux_rld = self.raw_data[market]['rld_data']['rld_da'].set_index('value_date')
                aux_rld.columns = [market + '_rld']
                da_data = da_data.merge(aux_rld,left_index=True,
                                              right_index=True, how='left')
            if 'av_cap_da' in self.raw_data[market]:
                aux_av_cap = self.raw_data[market]['av_cap_da']
                da_data = da_data.merge(aux_av_cap,left_index=True,
                                              right_index=True, how='left')
                av_cap_columns.extend(aux_av_cap.columns)
            if 'hydro_data_dict' in self.raw_data[market]:
                if 'hydro_da' in self.raw_data[market]['hydro_data_dict']:
                    aux_hydro = self.raw_data[market]['hydro_data_dict']['hydro_da'].set_index('value_date')           
                    aux_hydro.columns = [market + '_hydro']
                    da_data = da_data.merge(aux_hydro,left_index=True,
                                                  right_index=True, how='left')
            
        for market in markets:
            new_columns = pd.DataFrame(da_data[[f"{market}_rld"]].values-\
                                       da_data[av_cap_columns].values
                                       ,
                                       columns=[f"{col}_{market}" for
                                                col in av_cap_columns],
                                       index=da_data.index)
            da_data = pd.concat([da_data, new_columns], axis=1)
            
        da_data = da_data.drop(av_cap_columns,axis=1)
        da_data = da_data.ffill()
        da_data = self.create_features_da(da_data)
        da_data = da_data.loc[da_data.index.date!=dt.date(2024,6,26)].copy()
        return da_data
    
    
    def create_features_da(self, da_data, features=['ghr', 'mcr']):
        markets = np.unique(self.params_dict['market_list'])
        for market in markets:
            da_data[market + '_ghr'] = da_data[market]/(da_data['ttf_da'] + da_data['eua']*0.2)
        da_data['mcr'] = (da_data['ttf_da'] + da_data['eua']*0.2)/\
            (da_data['spot_coal']/6.5+da_data['eua']*0.35)
        return da_data
    
    

    def train_dict_markets_loop(self, markets,
                                da_data, train_dict,
                                y):
        for market in markets:
            aux = da_data.loc[:self.pivot_date+dt.timedelta(days=1,hours=-1)].copy()
            other_markets = [a for a in markets if a != market]
            for drop_market in other_markets:
                for drop_data in ['', '_ghr']:
                    aux.drop(drop_market+drop_data, axis=1, inplace=True)
            # aux = aux.dropna()
            aux = aux.fillna(0)
            aux_y = aux[market + '_' + y]
            aux_x = aux.drop([market, market + '_' + y], axis=1)
            aux_indices = aux_x.index
            aux_cols = aux_x.columns
            x_train = aux_x.values
            y_train = aux_y.values.flatten()
            train_dict[market] = aux_cols, x_train, y_train, aux_indices
        return train_dict
    
    
    def create_train_data(self, da_data, fcst_range=None, y='ghr'):
    
        markets = np.unique(self.params_dict['market_list'])
        train_dict = {}
        if fcst_range is None:
            train_dict = self.train_dict_markets_loop(markets,
                                        da_data, train_dict,
                                        y)
        else:
            for fcst_date in fcst_range:
                self.set_pivot_date(fcst_date)
                train_dict[fcst_date] = {}
                train_dict[fcst_date] = self.train_dict_markets_loop(markets,
                                            da_data, train_dict,
                                            y)
        return train_dict
    
        
    
    """
    To initiate model insert model_params_dict which will have this structure:
        models_params_dict['model'] = {'model name': {'n_estimators': 100,
                                                     'max_depth': 5,
                                                     'learning_rate': 0.05}
                                                    structure of actual parameters for each individual model
                                                    will be 'key' = name of model parameter
                                                            'value' = value of parameter
    """
    
    def init_model(self, models_params_dict):
        for model_name, model_params in models_params_dict.items():
            if 'xgboost' in model_name:
                self.models_inst[model_name] = XGBRegressor(**model_params)
            elif 'extratrees' in model_name:
                self.models_inst[model_name] = ExtraTreesRegressor(**model_params)
                
                
    def init_scaler(self, train_dict_keys,
                    models_params_dict,
                    scaler='yeojohnson'):
        self.scaler = {}
        for model_name, model_inst in models_params_dict.items():          
            
                if scaler in ['standardscaler']:
                    self.scaler = StandardScaler()
                elif scaler in ['yeojohnson']:
                    #Yeo-Johnson and standardizing are defaults
                    self.scaler = PowerTransformer()
            
                
    def fit_model(self, train_dict, models_params_dict):
        if not hasattr(self, 'fitted_models_dict'):
            self.fitted_models_dict = {}
        self.init_scaler(train_dict.keys(), models_params_dict)
        for model_name, model_params in models_params_dict.items():   
            if model_name not in list(self.fitted_models_dict):
                self.fitted_models_dict[model_name] = {}
            
            
            markets_list = train_dict.keys()
            
            for market in markets_list:
                x_train = train_dict[market][1]
                y_train = train_dict[market][2]
                
                scaled_data = self.scaler.fit_transform(x_train)
                if market not in list(self.fitted_models_dict[model_name]):
                    if 'xgboost' in model_name:
                        self.fitted_models_dict[model_name][market] = XGBRegressor(**model_params[market]).fit(scaled_data,
                                                                                             y_train)
                    elif 'extratrees' in model_name: 
                        self.fitted_models_dict[model_name][market] = ExtraTreesRegressor(**model_params[market]).fit(scaled_data,
                                                                                             y_train)
        
    """
    Here I need to collect data for forecasting
    Problem with insuffiecient liquidity will be solved with adjusting last settlement values
    with change in the front month contract
    """
      
    def assemble_fcst_predictors(self, train_dict):
        """
        Structure this so that each contract for params_dict will have its own df/array
        of data to forecast from
        
        Data to assamble:
            RLD
            AvCap
            fual prices

        Returns
        -------
        None.

        """
        self.fcst_data = {}
        fcst_data = pd.DataFrame()
        av_cap_cols = []
        for data_type, data in self.raw_data.items():
            if data_type in ['fuels_da', 'power_da']:
                continue
            elif data_type in ['fuels_fut']:
                aux = self.create_fuels_curve()
                
            else:
                aux = self.create_fund_curve(data['rld_data']['nominal_matrix'], 'rld', data_type)
                if 'av_cap_fcst' in list(data):
                    aux_cap = data['av_cap_fcst']
                    av_cap_cols.extend(aux_cap.columns)
                    # assert len(aux) == len(aux_cap)
                    # aux = pd.concat([aux, aux_cap],axis=1)
                    aux = aux.merge(aux_cap, left_index=True, right_index=True,
                                    how='left')
                if 'hydro_data_dict' in list(data):
                    aux_hydro = self.create_fund_curve(data['hydro_data_dict']['nominal_matrix'],
                                                       'hydro',data_type)
                    aux = pd.concat([aux, aux_hydro],axis=1)
            if fcst_data.empty:
                fcst_data = aux.copy()
            else:
                fcst_data = pd.concat([fcst_data, aux],axis=1)
        rld_columns = [a for a in fcst_data.columns if 'rld' in a]
        for rld_market in rld_columns:
            market_aux = rld_market.split('_')[0]
            # Vectorized operation
            new_columns = pd.DataFrame(fcst_data[[rld_market]].values-\
                                       fcst_data[av_cap_cols].values,
                                       columns=[f"{col}_{market_aux}" for
                                                col in av_cap_cols],
                                       index=aux.index)
            
            # Concatenate the new columns to the original DataFrame
            fcst_data = pd.concat([fcst_data, new_columns], axis=1)
        fcst_data.drop(av_cap_cols,axis=1,inplace=True)
            
        fcst_data['mcr'] = (fcst_data['ttf_da'] + fcst_data['eua']*0.2)/\
            (fcst_data['spot_coal']/6.5+fcst_data['eua']*0.35)
        # fcst_data = fcst_data[train_dict[market][0].to_list()]
                    
                
        self.fcst_data = fcst_data
            
    def create_fund_curve(self, data, fund, market):
        aux = data.loc[[self.pivot_date]]
        aux.columns = aux.index[0] + pd.to_timedelta(aux.columns-1, unit='h')
        aux = aux.T
        aux = aux.loc[self.curve_start_date:self.curve_end_date].copy()
        aux.columns = [market + '_' + fund]
        return aux
        
            
    def fetch_fund_data_for_fcst(self, fund, del_start, del_end, markets='all'):

        fund_out = pd.DataFrame()
        if fund in ['rld']:
            source_dict = self.rld_data_dict
        elif fund in ['hydro']:
            source_dict = self.hydro_data_dict
        for market, market_dict in source_dict.items():
            if markets in ['all']:
                pass
            elif not market in markets:
                continue
            aux = market_dict['nominal_matrix'][market_dict['nominal_matrix'].index==self.pivot_date].copy()
            if len(aux) == 0:
                print('684')
            aux.columns = aux.index[0] + pd.to_timedelta(aux.columns, unit='h')
            aux = aux.T
            aux = aux.loc[del_start:del_end].copy()
            aux.columns = [market + '_' + fund]
            if fund_out.empty:
                fund_out = aux.copy()
            else:
                fund_out = pd.concat([fund_out, aux],axis=1,join='inner')
        return fund_out
            
    def apply_coefficients(self, df):
        for key, coeffs in self.gas_coal_coefs.items():
            beta, intercept = coeffs
            
            # Extracting month and year from the key
            month_str, year = key.split('_')
            month = int(month_str.split('.')[1])
            year = int(year)
            
            # Filtering the DataFrame for the specific month and year
            mask = (df.index.month == month) & (df.index.year == year)
            
            # Apply the regression to the 'x' values to get the predicted 'y' values
            df.loc[mask, 'spot_coal'] = df.loc[mask, 'ttf_da'] * beta + intercept
        return df
    
    def transform_and_adjust(self, base_df, alt_df=None, rld_columns=None, target_columns=None, transform=True):
        
        
        df_copy = base_df.copy()

        if alt_df is not None and rld_columns is not None and target_columns is not None:
            
            # Replace '_rld' columns with alternative values
            for col in rld_columns:
                if col in alt_df.columns:
                    diff = base_df[col] - alt_df[col]
                    df_copy[col] = alt_df[col]

                    # Adjust target columns based on '_rld' column differences
                    for target_col in target_columns:
                        target_col_parts = target_col.split('_')
                        if len(target_col_parts) == 3 and target_col_parts[2] == col.split('_')[0]:
                            df_copy[target_col] -= diff
                            
        # Adjust coal price to match gas price based on fitted price
        df_copy = self.apply_coefficients(df_copy)

        if transform:        
            # Apply the fitted PowerTransformer to all columns
            try:
                df_copy[df_copy.columns] = self.scaler.transform(df_copy[df_copy.columns])
            except (ValueError, OptimizeWarning) as e:
                warnings.warn(f"Transformation failed for DataFrame: {e}")
                # Handle the failure case, return the original df_copy or handle as needed
                return df_copy

        return df_copy

    def get_curve_forecast(self, model_params_dict, scen_dict):
       
        
        self.fcst_curve_dict = {}
        self.data_collection = {}
        for fcst_date, fcst_dict in scen_dict.items():
            if (fcst_date.weekday() < 5) and (fcst_date not in holidays.DE()):
                pass
            else:
                continue
            self.clean_fcst_date_attributes()
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(self.pivot_date)
            self.update_params_dict(new_params_dict)
            self.assemble_raw_data()
            da_data = self.assemble_da_data()
            train_dict = self.create_train_data(da_data)
            self.fit_model(train_dict, model_params_dict)
            self.assemble_fcst_predictors(train_dict)
            fcst_data = self.fcst_data[train_dict['de'][0]]
            self.data_collection[fcst_date] = fcst_data
            rld_columns = [col for col in fcst_data.columns if '_rld' in col]
            
            target_columns = [col for col in fcst_data.columns if len(col.split('_')) == 3]
            self.fcst_curve_dict[fcst_date] = {}
            for scen_type, scen_type_dict in fcst_dict.items():
                self.fcst_curve_dict[fcst_date][scen_type] = {}
                if scen_type_dict:
                    transformed_dfs = Parallel(n_jobs=-1)(
                        delayed(self.transform_and_adjust)(fcst_data, df, df.columns, target_columns) 
                        for df in scen_type_dict.values()
                    )
                else:
                    transformed_dfs = [self.transform_and_adjust(fcst_data, None, rld_columns, target_columns)]
                       
                changed_dfs = [self.transform_and_adjust(fcst_data, df, df.columns, target_columns, transform=False)
                               for df in scen_type_dict.values()]
        
                
        
                for model_name, models_dict in self.fitted_models_dict.items():
                    self.fcst_curve_dict[fcst_date][scen_type][model_name] = {}
                    
                    for market in list(train_dict):
                        self.fcst_curve_dict[fcst_date][scen_type][model_name][market] = {}
                        fitted_model = models_dict[market]
                        final_data_dict = {}
                        for data_type in  ['ghr', 'nominal',]:
                            final_data_dict[data_type] = pd.DataFrame()
                            
                        y_train_pred = fitted_model.predict(self.scaler.transform(train_dict[market][1]))
                        
                        residuals, res_std = self.residuals_adjustment(train_dict, market,
                                                              y_train_pred, fcst_data)
                        fuels_costs_series = self.fcst_data['ttf_da']+self.fcst_data['eua']*0.2
                        
                        additional_data_list = [res_std,
                                                fuels_costs_series,
                                                fcst_data]
                        
                        

                        for i, predictors_data, raw_df in zip(range(len(transformed_dfs)),
                                                              transformed_dfs,
                                                              changed_dfs):
        
                            forecast_raw = pd.DataFrame(fitted_model.predict(predictors_data),
                                                    index=self.fcst_data.index,
                                                    columns=[i])
                            
                            
                            forecast = pd.DataFrame(forecast_raw.values - residuals.values,
                                                    index=forecast_raw.index,
                                                    columns=[i])
                            
                           
                            forecast_list = [forecast]
                            
                            fuels = raw_df['ttf_da'] + raw_df['eua']*0.2
                            
                            forecast_nominal_list = [pd.DataFrame((aux[i].values*
                                                             fuels.values),
                                                            index=self.fcst_data.index,
                                                            columns=[i]) for aux in
                                                     forecast_list]
                            final_data_list = forecast_list + forecast_nominal_list
                            for i, data_type in  enumerate(['ghr', 'nominal']):
                                if final_data_dict[data_type].empty:
                                    final_data_dict[data_type] = final_data_list[i]
                                else:
                                    final_data_dict[data_type] = pd.concat([final_data_dict[data_type],
                                                                            final_data_list[i]],
                                                                           axis=1)
                            
                               
                        for i, data_type in  enumerate(['ghr', 'nominal', 'std',
                                              'fuels_costs', 'fcst_data']):
                            if data_type in ['ghr', 'nominal']:                            
                                self.fcst_curve_dict[fcst_date][scen_type][model_name][market][data_type] = final_data_dict[data_type]
                            else:
                                self.fcst_curve_dict[fcst_date][scen_type][model_name][market][data_type] = additional_data_list[i-2]
                        
              
    def residuals_adjustment(self, train_dict, market,
                             y_train_pred,
                             fcst_data,
                             selected_features=['de_rld'],
                             adjustment_lookback=14,
                             std_lookback=360):
        
         
        
        # Define X_train, y_train
        index = train_dict[market][3][-adjustment_lookback*24:]
        X_train = train_dict[market][1][-adjustment_lookback*24:]
        
        y_train = train_dict[market][2][-adjustment_lookback*24:]
        y_train_for_std = train_dict[market][2][-std_lookback*24:]
        index_for_std = train_dict[market][3][-std_lookback*24:]
        features_index = [list(train_dict[market][0]).index(feature) for feature in selected_features]
        
        residuals = y_train_pred[-adjustment_lookback*24:] - y_train
        
        res_ser = pd.Series(index=fcst_data.index)
        
        for hour in range(24):
            model = LinearRegression()
            hours_mask = index.hour == hour
            X_train_filtered = X_train[hours_mask][:, features_index]
            fcst_data_filtered = fcst_data[fcst_data.index.hour==hour][selected_features].dropna()
            aux_residuals = residuals[hours_mask]
            model.fit(X_train_filtered,aux_residuals)
            
            residuals_pred_values = model.predict(fcst_data_filtered.values)
            
            res_ser.loc[res_ser.index.intersection(fcst_data_filtered.index)] = residuals_pred_values
        
        # Get the residuals for std calculation
        std_residuals =  y_train_pred[-std_lookback*24:] - y_train_for_std
        
        std_residuals_df = pd.DataFrame(std_residuals, index=index_for_std, columns=['residuals'])
        std_residuals_df[selected_features] = train_dict[market][1][-std_lookback*24:,features_index]
        
        # Calculate quantiles for each feature and store quantile bins and stds
        quantiles_dict = {}
        quantile_bins_dict = {}
        stds_dict = {}
        for feature in selected_features:
            quantiles, bins = pd.qcut(std_residuals_df[feature], q=10, labels=False, retbins=True, duplicates='drop')
            quantiles_dict[feature] = quantiles
            quantile_bins_dict[feature] = bins
            std_by_quantile = std_residuals_df.groupby(quantiles)['residuals'].std()
            stds_dict[feature] = std_by_quantile
        
        # Create a DataFrame for the standard deviations
        stds_df = pd.DataFrame(stds_dict)
        
        # Function to approximate combined std for multiple features
        def approximate_combined_std_multi(row):
            n = len(row)
            return np.sqrt(np.sum(row**2) / (n**2))
        
        # Generate all combinations of deciles
        decile_combinations = list(product(range(10), repeat=len(selected_features)))
        
        # Calculate combined standard deviation for each combination
        combined_stds_list = []
        for comb in decile_combinations:
            std_values = [stds_dict[selected_features[i]][comb[i]] for i in range(len(selected_features))]
            combined_std = approximate_combined_std_multi(pd.Series(std_values))
            combined_stds_list.append((*comb, combined_std))
        
        # Convert to DataFrame for better readability
        combined_stds_df = pd.DataFrame(combined_stds_list,
                                        columns=[f'{feature}_decile' for
                                                 feature in selected_features] + ['combined_std'])
        
        # Function to find the quantile bin for a value based on bins
        def find_quantile_bin(value, bins):
            for i in range(len(bins)-1):
                if bins[i] <= value < bins[i+1]:
                    return i
            return len(bins) - 2
        
        fcst_data_for_std = fcst_data[selected_features]
        
        # Find the quantile bin for each value in new_values_df
        new_values_quantiles = fcst_data_for_std.apply(lambda row: [find_quantile_bin(row[feature],
                                                                                  quantile_bins_dict[feature])
                                                                for feature in selected_features], axis=1)
        # Convert the quantile bins to a DataFrame
        new_values_quantiles_df = pd.DataFrame(new_values_quantiles.tolist(),
                                               columns=[f'{feature}_decile' for feature in selected_features],
                                               index=new_values_quantiles.index)
        residual_std = new_values_quantiles_df.merge(combined_stds_df,
                                                  on=[f'{feature}_decile' for feature in selected_features],
                                                  how='left').set_index(new_values_quantiles.index)
        residual_std = residual_std[['combined_std']].copy()
        
        
        return pd.DataFrame(res_ser), residual_std
            
            
            
        
        
        
        
            
    @staticmethod
    def average_models(nested_dict):
        new_dict = {}
    
        for key1, subdict1 in nested_dict.items():
            new_dict[key1] = {}
            for key2, subdict2 in subdict1.items():
                new_dict[key1][key2] = {}
                # Initialize a dictionary to collect DataFrames by key4 and key5
                collected_dfs = {}
                for key3, subdict3 in subdict2.items():
                    for key4, subdict4 in subdict3.items():
                        for key5, df in subdict4.items():
                            if (key4, key5) not in collected_dfs:
                                collected_dfs[(key4, key5)] = []
                            collected_dfs[(key4, key5)].append(df)
                # Compute the average of collected DataFrames
                
                for (key4, key5), dfs in collected_dfs.items():
                    if len(dfs) == 1:
                        avg_df = dfs[0]
                    else:
                        if 'std' not in key5:
                            avg_df = sum(dfs) / len(dfs)
                        else:
                            pass
                    if key4 not in new_dict[key1][key2]:
                        new_dict[key1][key2][key4] = {}
                    new_dict[key1][key2][key4][key5] = avg_df
        
        return new_dict
    
    @staticmethod
    def reorganize_dict(nested_dict):
        new_dict = {}

        for key1, subdict1 in nested_dict.items():
            for key2, subdict2 in subdict1.items():
                for key4, subdict3 in subdict2.items():
                    for key5, df in subdict3.items():
                        if key2 not in new_dict:
                            new_dict[key2] = {}
                        if key5 not in new_dict[key2]:
                            new_dict[key2][key5] = {}
                        if key1 not in new_dict[key2][key5]:
                            new_dict[key2][key5][key1] = {}
                        new_dict[key2][key5][key1][key4] = df

        return new_dict
    
    
    @staticmethod
    def apply_masks_and_compute_means(nested_dict, key2, key5, masks_dict):
        new_dict = {}
    
        def apply_date_range_filter(df, start_date, end_date):
            return df[(df.index >= start_date) & (df.index <= end_date)]
    
        def filter_business_hours(df):
            business_hours = (df.index.dayofweek < 5) & (df.index.hour >= 9) & (df.index.hour <= 20)
            return df[business_hours]
    
        if key2 in nested_dict:
            fcst_data_dict = nested_dict[key2]['fcst_data']
            std_data_dict = nested_dict[key2]['std']
            if key5 in nested_dict[key2]:
                for key1, subdict1 in nested_dict[key2][key5].items():
                    fcst_data_date_dict = fcst_data_dict[key1]
                    std_data_date_dict = std_data_dict[key1]
                    masks = masks_dict[key1]
                    for key4, df in subdict1.items():
                        fcst_data = fcst_data_date_dict[key4][['eua', 'ttf_da']].copy()
                        fcst_data['gas_cost'] = fcst_data['ttf_da'] + fcst_data['eua']*0.2
                        fcst_data = fcst_data[['gas_cost']].copy()
                        std_data = std_data_date_dict[key4]
                        mean_values = []
                        std_values = []
                        index_tuples = []
                        fuels_list = []
                        for mask_vars in masks:
                            product, year, delivery, start_date, end_date = mask_vars
                            masked_df = apply_date_range_filter(df, start_date, end_date)
                            masked_fuels = apply_date_range_filter(fcst_data, start_date, end_date)
                            masked_std = apply_date_range_filter(std_data,start_date, end_date)
                            if key5 in ['nominal']:
                                masked_std.loc[:, 'combined_std'] = (masked_std.values * masked_fuels.values).flatten()
                            if delivery == 'base':
                                mean_series = masked_df.mean(axis=0).to_list()                                
                                mean_std = np.sqrt(np.mean(masked_std.values**2))
                            elif delivery == 'peak':
                                masked_df = filter_business_hours(masked_df)
                                masked_std = filter_business_hours(masked_std)
                                mean_series = masked_df.mean(axis=0).iloc[0]
                                mean_std = np.sqrt(np.mean(masked_std.values**2))
                            else:
                                continue
                            
                            fuels_list.append(masked_fuels.mean(axis=0).iloc[0])
                            mean_values.append(mean_series)
                            std_values.append(mean_std)
                            index_tuples.append((product, year, delivery))
                        constructed_dict = {}
                        # Combine all means into a DataFrame with a multi-level index
                        constructed_dict['mean'] = pd.DataFrame(mean_values,
                                                      index=pd.MultiIndex.from_tuples(index_tuples, names=['product', 'year', 'delivery']),
                                                      columns=[masked_df.columns])
                        constructed_dict['std'] = pd.DataFrame(std_values,
                                                      index=pd.MultiIndex.from_tuples(index_tuples, names=['product', 'year', 'delivery']),
                                                      columns=['std'])
                        constructed_dict['fuels'] = pd.DataFrame(fuels_list,
                                                      index=pd.MultiIndex.from_tuples(index_tuples, names=['product', 'year', 'delivery']),
                                                      columns=['fuels'])
                        # constructed_dict['lower'] = pd.DataFrame((constructed_dict['mean'] -
                        #                                          2*constructed_dict['std'].values),
                        #                               index=pd.MultiIndex.from_tuples(index_tuples, names=['product', 'year', 'delivery']),
                        #                               columns=[str(i) + '_lower' for i
                        #                                        in masked_df.columns])
                        # constructed_dict['upper'] = pd.DataFrame((constructed_dict['mean'] +
                        #                                          2*constructed_dict['std'].values),
                        #                               index=pd.MultiIndex.from_tuples(index_tuples, names=['product', 'year', 'delivery']),
                        #                               columns=[str(i) + '_upper' for i
                        #                                        in masked_df.columns])
                        
                        
                        
                        
                        
    
                        if key1 not in new_dict:
                            new_dict[key1] = {}
    
                        new_dict[key1][key4] = constructed_dict
    
        return new_dict

    
    @staticmethod
    def create_country_spread_dict(input_dict):
        new_dict = {}
    
        for key1, subdict in input_dict.items():
            new_dict[key1] = {}
            key2_combinations = combinations(subdict.keys(), 2)
            
            
            for key2_1, key2_2 in key2_combinations:
                data_dict = {}
                dict1 = subdict[key2_1]
                dict2 = subdict[key2_2]
    
                key3 = '_'.join((key2_1,key2_2))
                data_dict['mean'] = dict1['mean'] - dict2['mean']
                data_dict['std'] = np.sqrt(dict1['std']**2+dict2['std']**2)
                data_dict['lower'] = data_dict['mean'] - 2*data_dict['std'].values
                data_dict['upper'] = data_dict['mean'] + 2*data_dict['std'].values
    
                new_dict[key1][key3] = data_dict
    
        return new_dict

    def get_product_forecast(self, model_params_dict,
                             aux_dict,
                             scenario_type='liq',
                             fcst_value_type='nominal'):
        if not hasattr(self, 'fcst_curve_dict'):
            self.get_curve_forecast(model_params_dict, aux_dict)
            
        mask_dict = {}
        for fcst_date, _ in self.fcst_curve_dict.items():
            mask_list = []
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(self.pivot_date)
            self.update_params_dict(new_params_dict)
            unique_product, unique_del, unique_year = self.drop_duplicates_from_multiple_lists(self.params_dict['product_list'],
                                                                                               self.params_dict['delivery_list'],
                                                                                               self.params_dict['year_list'])
            for product, delivery, year in zip(unique_product, unique_del, unique_year):
                del_start, del_end = self.get_start_end_product_date(product, delivery, year)
                mask_list.append([product, year, delivery, del_start, del_end])
                
            mask_dict[fcst_date] = mask_list
                
            
        model_avg_fcst_dict = self.average_models(self.fcst_curve_dict)
        reorganized_fcst_dict = self.reorganize_dict(model_avg_fcst_dict)
        
        prod_dict = self.apply_masks_and_compute_means(reorganized_fcst_dict,
                                                       scenario_type,
                                                       fcst_value_type,
                                                       mask_dict)
        
        return prod_dict
    
    def get_country_spread(self,model_params_dict,
                             aux_dict,
                             scenario_type='liq',
                             fcst_value_type='nominal'):
        prod_dict = self.get_product_forecast(model_params_dict,
                                 aux_dict,
                                 scenario_type,
                                 fcst_value_type)
        
        self.prod_dict = prod_dict
        
        spread_dict = self.create_country_spread_dict(prod_dict)
        
        return spread_dict
    
    def get_base_peak_spread(self,model_params_dict,
                             aux_dict,
                             scenario_type='liq',
                             fcst_value_type='nominal'):
        
        prod_dict = self.get_product_forecast(model_params_dict,
                                 aux_dict,
                                 scenario_type,
                                 fcst_value_type)
        
        new_dict = {}
        for fcst_date, country_dict in prod_dict.items():
            new_dict[fcst_date] = {}
            for country, df in country_dict.items():
                pivot_df = df.pivot_table(index=['product', 'year'], columns='delivery', values=0, aggfunc='sum')

                # Calculate the difference
                pivot_df[0] = pivot_df['base'] - pivot_df['peak']
                new_dict[fcst_date][country] = pivot_df
                
        return new_dict
    
    def get_calendar_spread(self,model_params_dict,
                             aux_dict,
                             scenario_type='liq',
                             fcst_value_type='nominal'):
        
        prod_dict = self.get_product_forecast(model_params_dict,
                                 aux_dict,
                                 scenario_type,
                                 fcst_value_type)
        
        self.prod_dict = prod_dict
        
        calendar_spread_dict = {}
        for fcst_date, fcst_dict in prod_dict.items():
            calendar_spread_dict[fcst_date] = {}
            for country, country_df in fcst_dict.items():
                calendar_spread_dict[fcst_date][country] = self.create_calendar_spread(country_df)
                
        return calendar_spread_dict
    
    def get_css(self,model_params_dict,
                    aux_dict,
                    scenario_type='liq',
                    fcst_value_type='nominal'):
        self.clean_fcst_date_attributes()
        prod_dict = self.get_product_forecast(model_params_dict,
                                 aux_dict,
                                 scenario_type,
                                 fcst_value_type)
        
        css_dict = {}
        for date, date_dict in prod_dict.items():
            css_dict[date] = {}
            for market, market_dict in date_dict.items():
                data_dict = {}
                data_dict['mean'] = market_dict['mean'] - 2*market_dict['fuels'].values
                data_dict['std'] = market_dict['std']
                data_dict['lower'] = data_dict['mean'] - 2*market_dict['std'].values
                data_dict['higher'] = data_dict['mean'] + 2*market_dict['std'].values
                data_dict['fuels'] = market_dict['fuels']
                
                
                css_dict[date][market] = data_dict
        
        return css_dict
        
    @staticmethod
    def create_calendar_spread(input_df):
        # Reset the index and prepare tuples for MultiIndex
    
        input_df = input_df.reset_index()
        row_tuples = [(p, y, d) for p, y, d in zip(input_df['product'], input_df['year'], input_df['delivery'])]
        tuple_index = pd.MultiIndex.from_tuples(row_tuples, names=['product', 'year', 'delivery'])
    
        mean_dfs = []
        std_dfs = []
        mean_minus_2std_dfs = []
        mean_plus_2std_dfs = []
    
        # Iterate over each numerical column in the input DataFrame
        for col in input_df.columns[3:]:  # Assuming the first three columns are not numerical
            if 'mean' in col:  # Handling mean columns
                # Compute the difference matrix for this column (row - column)
                column_values = input_df[col].values
                difference_matrix = np.subtract.outer(column_values, column_values)
    
                # Get upper triangular indices excluding the diagonal
                upper_tri_indices = np.triu_indices_from(difference_matrix, k=1)
    
                # Get the valid values from the upper triangular part
                upper_valid_values = difference_matrix[upper_tri_indices]
    
                # Create pairs of tuples from the tuple_index using upper_tri_indices
                upper_row_tuples = [tuple_index[i] for i in upper_tri_indices[0]]
                upper_col_tuples = [tuple_index[i] for i in upper_tri_indices[1]]
                index_tuples = list(zip(upper_row_tuples, upper_col_tuples))
    
                # Create DataFrame
                upper_df = pd.DataFrame({
                    'Row': upper_row_tuples,
                    'Column': upper_col_tuples,
                    f'Difference_{col}': upper_valid_values
                })
    
                mean_dfs.append(upper_df)
            
            elif 'std' in col:  # Handling std columns
                # Compute the standard deviation for the spread
                column_values = input_df[col].values
                std_spread_matrix = np.sqrt(np.add.outer(np.square(column_values), np.square(column_values)))
    
                # Get upper triangular indices excluding the diagonal
                upper_tri_indices = np.triu_indices_from(std_spread_matrix, k=1)
    
                # Get the valid values from the upper triangular part
                upper_valid_values = std_spread_matrix[upper_tri_indices]
    
                # Create pairs of tuples from the tuple_index using upper_tri_indices
                upper_row_tuples = [tuple_index[i] for i in upper_tri_indices[0]]
                upper_col_tuples = [tuple_index[i] for i in upper_tri_indices[1]]
                index_tuples = list(zip(upper_row_tuples, upper_col_tuples))
    
                # Create DataFrame
                upper_df = pd.DataFrame({
                    'Row': upper_row_tuples,
                    'Column': upper_col_tuples,
                    f'Std_Spread_{col}': upper_valid_values
                })
    
                std_dfs.append(upper_df)
    
        results = {}
    
        # Merge mean and std DataFrames on 'Row' and 'Column'
        if mean_dfs and std_dfs:
            combined_mean_df = pd.concat(mean_dfs, axis=1)
            combined_std_df = pd.concat(std_dfs, axis=1)
            combined_mean_df = combined_mean_df.loc[:, ~combined_mean_df.columns.duplicated()]
            combined_std_df = combined_std_df.loc[:, ~combined_std_df.columns.duplicated()]
    
            results['mean_df'] = combined_mean_df
            results['std_df'] = combined_std_df
    
            # Calculate mean - 2*std and mean + 2*std
            mean_cols = [col for col in combined_mean_df.columns if 'Difference_mean' in col]
            std_cols = [col for col in combined_std_df.columns if 'Std_Spread' in col]
    
            for mean_col, std_col in zip(mean_cols, std_cols):
                mean_minus_2std_df = combined_mean_df[['Row', 'Column']].copy()
                mean_minus_2std_df[f'{mean_col}_minus_2std'] = combined_mean_df[mean_col] - 2 * combined_std_df[std_col]
                mean_minus_2std_dfs.append(mean_minus_2std_df)
    
                mean_plus_2std_df = combined_mean_df[['Row', 'Column']].copy()
                mean_plus_2std_df[f'{mean_col}_plus_2std'] = combined_mean_df[mean_col] + 2 * combined_std_df[std_col]
                mean_plus_2std_dfs.append(mean_plus_2std_df)
    
            combined_mean_minus_2std_df = pd.concat(mean_minus_2std_dfs, axis=1)
            combined_mean_plus_2std_df = pd.concat(mean_plus_2std_dfs, axis=1)
            combined_mean_minus_2std_df = combined_mean_minus_2std_df.loc[:, ~combined_mean_minus_2std_df.columns.duplicated()]
            combined_mean_plus_2std_df = combined_mean_plus_2std_df.loc[:, ~combined_mean_plus_2std_df.columns.duplicated()]
    
            results['mean_minus_2std_df'] = combined_mean_minus_2std_df
            results['mean_plus_2std_df'] = combined_mean_plus_2std_df
        else:
            results['mean_df'] = pd.DataFrame()
            results['std_df'] = pd.DataFrame()
            results['mean_minus_2std_df'] = pd.DataFrame()
            results['mean_plus_2std_df'] = pd.DataFrame()
    
        return results  


        
    def clean_fcst_date_attributes(self):
        #Clear input forecast data
        if hasattr(self, 'raw_data'):
            if 'fuels_fut' in list(self.raw_data):
                del self.raw_data['fuels_fut']
        #Clear input forecast data
        if hasattr(self, 'fcst_data'):
            del self.fcst_data
        #Clear input forecast data
        if hasattr(self, 'base_fcst_data'):
            del self.base_fcst_data
        # Clear scaled input forecast data
        if hasattr(self, 'fcst_model_data'):
            del self.fcst_model_data
        # Clear fitted model dict
        if hasattr(self, 'fitted_models_dict'):
            del self.fitted_models_dict
        # Clear forecasted curve dict
        if hasattr(self, 'curve_start_date'):
            del self.curve_start_date
            del self.curve_end_date

            
            
    def clean_attributes_for_scenario_run(self):
        # Clear scaled input forecast data
        if hasattr(self, 'fcst_model_data'):
            del self.fcst_model_data
            # Clear forecasted curve dict
            if hasattr(self, 'fcst_curve_dict'):
                del self.fcst_curve_dict
    def create_base_fcst_data_deepcopy(self):
        self.base_fcst_data = copy.deepcopy(self.fcst_data)

        
    
    def get_future_week_number(self, weeks_ahead):
        # Calculate the future date by adding the specified number of weeks to the current date
        future_date = self.pivot_date + timedelta(weeks=weeks_ahead)
        # Return the ISO week number of the future date
        return future_date.isocalendar()[1]
    
    
    def transform_params_dict(self, pivot):
        base_dict = copy.deepcopy(self.original_params_dict)
        products_list = base_dict['product_list']
        rel_tenors_list = [a.split('_')[1] for a in
                        products_list]
        periods_list = [a.split('_')[0] for a in
                        products_list]
        
        dates_list = [start_date(pivot, product) if product.lower() not in ['wk', 'wknd'] else
                      start_date(pivot, 'w') if product.lower() in ['wk'] else None
                      for product in products_list]
        fix_tenor_list = [self.get_future_week_number(int(c)) if b.lower() in ['w', 'wk', 'wknd'] else
                          a.month if b in ['M'] else
                          (a.month-1)//3+1 if b in ['Q'] else
                          1 if b in ['Y'] else None for a, b, c in
                          zip(dates_list,periods_list, rel_tenors_list)]
        transformed_products_list = [a + '.' + str(b)
                                     for a, b in
                                     zip(periods_list, fix_tenor_list)]
        transformed_years_list = [a.year for a in dates_list]
        new_dict = base_dict
        new_dict['product_list'] = transformed_products_list
        new_dict['year_list'] = transformed_years_list
        return new_dict
        
    def get_fcst_for_range(self, fcst_range, model_params_dict, nominal=True):
        tot_curves_dict = {}
        self.data_collection = {}
        
        # da_data = self.assemble_da_data()
        for fcst_date in fcst_range:
            self.clean_fcst_date_attributes()
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(fcst_date)
            self.update_params_dict(new_params_dict)
            self.assemble_raw_data()
            da_data = self.assemble_da_data()

            train_dict = self.create_train_data(da_data)
            curve_dict = self.get_product_forecast(train_dict,
                                                   model_params_dict)
            self.data_collection[fcst_date] = self.fcst_data
            # aux_curve_data = pd.DataFrame()
            # for fcst_type, fcst_type_df in curve_dict.items():
            #     fcst_type_df.columns = [a + '_' + fcst_type for a in fcst_type_df.columns]
            #     if aux_curve_data.empty:
            #         aux_curve_data = fcst_type_df.copy()
            #     else:
            #         aux_curve_data = pd.concat([aux_curve_data,
            #                                     fcst_type_df],axis=1)
            # self.data_collection[fcst_date] = pd.concat([aux_fcst_data,
            #                                              aux_curve_data], axis=1)
                
            tot_curves_dict[fcst_date] = curve_dict
            

            
        return tot_curves_dict
    
    def insert_scenario(self, scenario_df):
        if not hasattr(self, 'base_fcst_data'):
            self.base_fcst_data = copy.deepcopy(self.fcst_data)
        start_date = self.fcst_data.index[0]
        end_date = self.fcst_data.index[-1]
        scenario_aux = scenario_df[start_date:end_date].copy()
        self.fcst_data[scenario_aux.columns] = scenario_aux
        rld_diff = (self.base_fcst_data[scenario_aux.columns]-
                    self.fcst_data[scenario_aux.columns])
        for col in rld_diff.columns:
            c = col.split('_')[0]
            for av_col in self.fcst_data.columns:
                split_col = av_col.split('_')
                if len(split_col) == 3:
                    c_match = split_col[-1]
                    if c_match == c:
                        self.fcst_data[av_col] -= rld_diff[col]
    
    
    def get_scenario_forecast(self,
                              model_params_dict,
                              scenario_data_dict: dict == {}):
        scenario_curves_dict = {}
        self.data_collection = {}
        
        for fcst_date, fcst_dict in scenario_data_dict.items():
            self.clean_fcst_date_attributes()
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(fcst_date)
            self.update_params_dict(new_params_dict)
            self.assemble_raw_data()
            da_data = self.assemble_da_data()
            train_dict = self.create_train_data(da_data)
            self.assemble_fcst_predictors(train_dict)
            if not hasattr(self, 'base_fcst_data'):
                self.base_fcst_data = copy.deepcopy(self.fcst_data)
            for scen_type, scen_type_dict in fcst_dict.items():
                counter = 0
                for scen, scen_df in scen_type_dict.items():
                    start_time = time.time()
                    
                    self.clean_attributes_for_scenario_run()
                    self.fcst_data = copy.deepcopy(self.base_fcst_data)
                    self.insert_scenario(scen_df)
                    curve_dict = self.get_curve_forecast(train_dict,
                                                           model_params_dict)
                    scenario_curves_dict[fcst_date] = curve_dict
                    if counter < 5:
                        elapsed_time = time.time() - start_time
                        print(f"Scen: {scen}, Time: {elapsed_time:.6f} seconds")
                        counter += 1
                    else:
                        break
                
                # scen_aux = scen_df[self.curve_start_date:self.curve_end_date].copy()
                
        
        
        return scenario_curves_dict
            
            
            
            
        

        
        
        
                
                        
                        
                            
        
                            
                
                    
                        
                        
                        
                
                
            
            
        
        
            
        
        
            
            
        
        
        
    
    
        
            
            
        
    
    
        
    
    
    


