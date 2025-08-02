# -*- coding: utf-8 -*-
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
        self._original_params_dict = params_dict.copy()
        self._rm_inst = None
        self._am_inst = None
        self._pivot_date = pd.to_datetime(dt.datetime.now().date())
        self._models_inst = {}
        self._scalers_inst = {}

        

    
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
        if delivery in ['peak']:
            del_end = self.get_nearest_older_business_day(del_end)
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
        if not hasattr(self,'rld_data_dict'):
            self.rld_data_dict = {}
        for market in markets:
            if not market in list(self.rld_data_dict):
                self.rld_data_dict[market] = {}
            if not 'nominal_matrix' in list(self.rld_data_dict[market]):
                # if 'nominal_matrix' not in list(self.rld_data_dict[market]):
                self.rld_data_dict[market]['nominal_matrix'] = self.rm_inst.get_fund_curve('ResidualDemand', 
                                                                                  '00', normalize_to=None,
                                                                                  market=market, source=source,
                                                                                  fut_periods=fut_periods)
            if not 'rld_da' in list(self.rld_data_dict[market]):
                # if 'da_data' not in list(self.rld_data_dict[market]):
                self.rld_data_dict[market]['rld_da'] = self.rm_inst.get_da_data(self.rld_data_dict[market]['nominal_matrix'])
                
    def get_hydro_data(self, source='db'):
        markets = [ 'fr', 'at']
        fut_periods = self.get_futures_periods()
        if not hasattr(self,'hydro_data_dict'):
            self.hydro_data_dict = {}
        for market in markets:
            if not market in list(self.hydro_data_dict):
                self.hydro_data_dict[market] = {}
            if not 'nominal_matrix' in list(self.hydro_data_dict[market]):
                # if 'nominal_matrix' not in list(self.rld_data_dict[market]):
                self.hydro_data_dict[market]['nominal_matrix'] = self.rm_inst.get_fund_curve('INF', 
                                                                                  '00', normalize_to=None,
                                                                                  market=market, source=source,
                                                                                  fut_periods=fut_periods)
            if not 'hydro_da' in list(self.hydro_data_dict[market]):
                # if 'da_data' not in list(self.rld_data_dict[market]):
                self.hydro_data_dict[market]['hydro_da'] = self.rm_inst.get_da_data(self.hydro_data_dict[market]['nominal_matrix'])
                    
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
            aux = self.am_inst.get_data_da(market=market, source=source)
            if av_cap.empty:
                av_cap = aux.copy()
            else:
                av_cap = pd.concat([av_cap, aux], axis=1, join='inner')
        self.av_cap_da = av_cap
    
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
        av_cap_fcst_list = []        
        
        for product, delivery, year in zip(self.params_dict['product_list'],
                                           self.params_dict['delivery_list'],
                                           self.params_dict['year_list']):
            aux_markets = pd.DataFrame()
            del_start, del_end = self.get_start_end_product_date(product, delivery, year)
            for market in markets:
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
                if aux_markets.empty:
                    aux_markets = aux.copy()
                else:
                    aux_markets = pd.concat([aux_markets, aux], axis=1, join='inner')
            av_cap_fcst_list.append(aux_markets)
        self.av_cap_fcst_list = av_cap_fcst_list
            
        
                
    
    def create_fuels_data_dict(self, gas_list,
                               coal_list, eua_list):
        fuels_params_dict = {}
        fuels_params_dict['market_list'] = gas_list + coal_list + eua_list
        fuels_params_dict['product_list'] = self.params_dict['product_list'] * 3
        fuels_params_dict['delivery_list'] = self.params_dict['delivery_list'] * 3
        # fuels_params_dict['delivery_list'] = [a if a =='base' else 'base' for a in 
        #                                       self.params_dict['delivery_list']] * 3
        fuels_params_dict['year_list'] = self.params_dict['year_list'] * 3
        fuels_params_dict['sD'] = self.params_dict['sD']
        fuels_params_dict['eD'] = self.params_dict['eD']
        fuels_params_dict['nl'] = self.params_dict['ns']
        fuels_params_dict['cont'] = False
        return self.drop_duplicates_from_fuels_dict(fuels_params_dict)
    
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
        
    def get_fuels_data(self):
        
        no_of_products = len(self.params_dict['product_list'])
        gas_list = ['gas'] * no_of_products
        coal_list = ['coal'] * no_of_products
        eua_list = ['eua'] * no_of_products
        fuels_params_dict = self.create_fuels_data_dict(gas_list, coal_list, eua_list)

        if not hasattr(self, 'fuels_fut'):
            fm_inst = FM(fuels_params_dict)
            self.fuels_fut = fm_inst.get_data(reference_date=self.pivot_date)

        if not hasattr(self, 'fuels_da'):
            sm_inst = SM(fuels_params_dict)
            self.fuels_da = sm_inst.get_spot_data_raw().ffill()                 
        
        
    
    def get_power_data(self):
        # if not hasattr(self, 'power_fut'):
        #     fm_inst = FM(self.params_dict)
        #     self.power_fut = fm_inst.get_data()
        if not hasattr(self, 'power_da'):
            sm_inst = SM(self.params_dict)
            self.power_da = sm_inst.get_spot_data_raw()
        
    
    def assemble_da_data(self, source='db'):
        
        self.get_rld_data(source=source)
        
        if not hasattr(self, 'rld_da'):
            self.get_rld_data()
        if not hasattr(self, 'hydro_da'):
            self.get_hydro_data()
        if not hasattr(self, 'power_da'):
            self.get_power_data()
        if not hasattr(self, 'fuels_da'):
            self.get_fuels_data()
        if not hasattr(self, 'av_cap_da'):
            self.get_av_cap_da()
        da_data = self.power_da.merge(self.fuels_da,left_index=True,
                                      right_index=True, how='left')
        da_data = da_data.merge(self.av_cap_da,left_index=True,
                                      right_index=True, how='left')
        for fund in ['rld', 'hydro']:
            if fund in ['rld']:
                source_dict = self.rld_data_dict
            elif fund in ['hydro']:
                source_dict = self.hydro_data_dict
            for market, data_dict in source_dict.items():
                aux = data_dict[fund + '_da']
                if 'value_date' in aux.columns:
                    aux.set_index('value_date', inplace=True)
                aux.columns = [market + '_' + fund]
                da_data = da_data.merge(aux,left_index=True,
                                        right_index=True, how='left')
                if fund in ['rld']:
                    # Vectorized operation
                    new_columns = pd.DataFrame(da_data[[f"{market}_rld"]].values-\
                                               da_data[self.av_cap_da.columns].values
                                               ,
                                               columns=[f"{col}_{market}" for
                                                        col in self.av_cap_da.columns],
                                               index=da_data.index)
                # new_columns = new_columns.iloc[:,:-1].copy()
                # # Rename new columns
                # new_columns.columns = [f"{col}_{market}" for col in self.av_cap_da.columns]
                
                # Concatenate the new columns to the original DataFrame
                    da_data = pd.concat([da_data, new_columns], axis=1)
            
        da_data = da_data.drop(self.av_cap_da.columns,axis=1)
        da_data = da_data.ffill()
        da_data = self.create_features_da(da_data)
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
            aux = aux.dropna()
            aux_y = aux[market + '_' + y]
            aux_x = aux.drop([market, market + '_' + y], axis=1)
            aux_cols = aux_x.columns
            x_train = aux_x.values
            y_train = aux_y.values.flatten()
            train_dict[market] = aux_cols, x_train, y_train
        return train_dict
    def create_train_data(self, da_data, fcst_range=None, y='ghr'):
        # da_data = self.assemble_da_data()
        # da_data = self.create_features_da(da_data)
        
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
        # for market in markets:
        #     aux = da_data.loc[:self.pivot_date+dt.timedelta(days=1,hours=-1)].copy()
        #     other_markets = [a for a in markets if a != market]
        #     for drop_market in other_markets:
        #         for drop_data in ['', '_ghr']:
        #             aux.drop(drop_market+drop_data, axis=1, inplace=True)
        #     aux = aux.dropna()
        #     aux_y = aux[market + '_' + y]
        #     aux_x = aux.drop([market, market + '_' + y], axis=1)
        #     aux_cols = aux_x.columns
        #     x_train = aux_x.values
        #     y_train = aux_y.values.flatten()
        #     train_dict[market] = aux_cols, x_train, y_train
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
                    markets='all'):
        self.scalers_dict = {}
        for model_name, model_inst in models_params_dict.items():
            self.scalers_dict[model_name] = {}
            if markets in ['all']:
                markets_list = train_dict_keys
            else:
                markets_list = markets
            for market in markets_list:
                if models_params_dict[model_name][market]['scaler'] in ['standardscaler']:
                    self.scalers_dict[model_name][market] = StandardScaler()
                elif models_params_dict[model_name][market]['scaler'] in ['yeojohnson']:
                    #Yeo-Johnson and standardizing are defaults
                    self.scalers_dict[model_name][market] = PowerTransformer()
            
                
    def fit_model(self, train_dict, models_params_dict, markets='all'):
        if not hasattr(self, 'fitted_models_dict'):
            self.fitted_models_dict = {}
        self.init_scaler(train_dict.keys(), models_params_dict, markets=markets)
        for model_name, model_params in models_params_dict.items():   
            if model_name not in list(self.fitted_models_dict):
                self.fitted_models_dict[model_name] = {}
            
            if markets in ['all']:
                markets_list = train_dict.keys()
            else:
                markets_list = markets
            for market in markets_list:
                x_train = train_dict[market][1]
                y_train = train_dict[market][2]
                
                scaled_data = self.scalers_dict[model_name][market].fit_transform(x_train)
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
        # RLD data
        # self.get_rld_normal()
        self.get_av_cap_fcst()
        if not hasattr(self, 'fuels_fut'):
            self.get_fuels_data()
        # da_data = self.assemble_da_data()
        # train_dict = self.create_train_data(da_data)
        
        self.fcst_data = {}
        for i, market, product, delivery, year in zip(range(len(self.params_dict['market_list'])),
                                                      self.params_dict['market_list'],
                                                      self.params_dict['product_list'],
                                                       self.params_dict['delivery_list'],
                                                       self.params_dict['year_list']):
            # Fetch star and end date of periods
            del_start, del_end = self.get_start_end_product_date(product, delivery, year)
            # Create name for the forecast product
            data_name = market + '_' + product + '_' + str(year) + '_' + delivery
            # Fetch fuels data
            gas_name = 'gas_' + product + '_' + str(year) + '_' + delivery
            coal_name = 'coal_' + product + '_' + str(year) + '_' + delivery
            eua_name = 'eua_' + product + '_' + str(year) + '_' + delivery
            if not gas_name in self.fuels_fut.columns:
               del self.fuels_fut
               self.get_fuels_data()
            if not coal_name in self.fuels_fut.columns:
                print('509')
            if not eua_name in self.fuels_fut.columns:
                print('511')
                
            aux_fuels = self.fuels_fut[[gas_name, coal_name, eua_name]]
            aux_fuels.columns = ['ttf_da', 'spot_coal', 'eua']
            if aux_fuels.index[-1]<self.pivot_date:
                aux_fuels = aux_fuels.iloc[-1].copy()
            else:
                if self.pivot_date in aux_fuels.index:
                    aux_fuels = aux_fuels.loc[self.pivot_date].copy()
                else:
                    aux_fuels = aux_fuels.loc[:self.pivot_date].iloc[-1].copy()
            # Fetch av cap data
            aux_av_cap = self.av_cap_fcst_list[i]
            
            # Fetch rld data
            aux_rld = self.fetch_fund_data_for_fcst('rld', del_start, del_end)
            if len(aux_rld) == 0:
                print('641')
            
            # Fetch hydro data
            aux_hydro = self.fetch_fund_data_for_fcst('hydro', del_start, del_end)
            
            # Merge data together
            aux = pd.concat([aux_av_cap, aux_rld, aux_hydro], axis=1, join='inner')
            
            rld_columns = [a for a in aux.columns if 'rld' in a]
            for rld_market in rld_columns:
                market_aux = rld_market.split('_')[0]
                # Vectorized operation
                new_columns = pd.DataFrame(aux[[rld_market]].values-\
                                           aux[self.av_cap_fcst_list[i].columns].values,
                                           columns=[f"{col}_{market_aux}" for
                                                    col in self.av_cap_fcst_list[i].columns],
                                           index=aux.index)
                
                # Concatenate the new columns to the original DataFrame
                aux = pd.concat([aux, new_columns], axis=1)
                
            aux = aux.drop(self.av_cap_fcst_list[i].columns, axis=1)
            
            aux[aux_fuels.index.to_list()] = aux_fuels.values[0], aux_fuels.values[1], aux_fuels.values[2]
            aux['mcr'] = (aux['ttf_da'] + aux['eua']*0.2)/\
                (aux['spot_coal']/6.5+aux['eua']*0.35)
            if 'Coal_de_de' not in aux.columns:
                print('544')
            aux = aux[train_dict[market][0].to_list()]
            self.fcst_data[data_name] = aux
            
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
            
    def create_and_scale_fcst_predictors(self, train_dict, model_params_dict):
        if not hasattr(self, 'fcst_data'):
            self.assemble_fcst_predictors(train_dict)
        self.fcst_model_data = {}
        for model_name in model_params_dict.keys():
            self.fcst_model_data[model_name] = {}
            for data_name, data in self.fcst_data.items():
                aux_train = data.values
                if len(aux_train)==0:
                    print('572')
                aux_train_scaled = self.scalers_dict[model_name][data_name.split('_')[0]].transform(aux_train)
                self.fcst_model_data[model_name][data_name] = aux_train_scaled
            
    def get_forecast(self, train_dict, model_params_dict, markets_to_fit='all'):
        # Initialize models and scaler
        # self.init_model(model_params_dict)
        # self.init_scaler()
        # Fit model
        self.fit_model(train_dict, model_params_dict,
                       markets=markets_to_fit)
        # Assemble predictors for forescast, use create_and_scale_fcst_predictors
        # for getting scaled arrays (forecast predictors dfs are created as well)
        if not hasattr(self, 'fcst_model_data'):
            self.create_and_scale_fcst_predictors(train_dict, model_params_dict)
        #Foreast data
        self.fcst_dict = {}
        for model_name, models_dict in self.fitted_models_dict.items():
            self.fcst_dict[model_name] = {}
            self.fcst_dict[model_name]['ghr']={}
            self.fcst_dict[model_name]['nominal']={}
            for i, market, product, delivery, year in zip(range(len(self.params_dict['market_list'])),
                                                          self.params_dict['market_list'],
                                                          self.params_dict['product_list'],
                                                           self.params_dict['delivery_list'],
                                                           self.params_dict['year_list']):
                # Fetch star and end date of periods
                del_start, del_end = self.get_start_end_product_date(product, delivery, year)
                # Create name for the forecast product
                data_name = market + '_' + product + '_' + str(year) + '_' + delivery
                product_name = product + '_' + str(year)
                fitted_model = models_dict[market]
                predictors_data = self.fcst_model_data[model_name][data_name]
                forecast = fitted_model.predict(predictors_data)
                
                self.fcst_dict[model_name]['ghr'][data_name] = forecast
                
                fuels_fut_data = self.fuels_fut.loc[:self.pivot_date].iloc[-1]
                name_base = data_name.replace(market,'')
                gas_costs = fuels_fut_data['gas'+name_base]
                eua_costs = fuels_fut_data['eua'+name_base]
                gas_heat_costs = gas_costs + eua_costs*0.2
                forecast_nominal = forecast * gas_heat_costs
                self.fcst_dict[model_name]['nominal'][data_name] = forecast_nominal
                
                
    def get_processed_forecast(self, train_dict,
                             model_params_dict,
                             markets_to_fit='all'):
        if not hasattr(self, 'fcst_dict'):
            self.get_forecast(train_dict,model_params_dict,markets_to_fit)
        fcst_dict = self.fcst_dict
        self.processed_fcst_dict = {}
        self.processed_fcst_dict['ghr'] = {}
        self.processed_fcst_dict['nominal'] = {}
        for model, data_dict in fcst_dict.items():
            ghr_dict = data_dict['ghr']
            nominal_dict = data_dict['nominal']
            fcst_nominal_list = []
            fcst_ghr_list = []
            del_start_list = []
            del_end_list = []            
            for i, market, product, delivery, year in zip(range(len(self.params_dict['market_list'])),
                                                          self.params_dict['market_list'],
                                                          self.params_dict['product_list'],
                                                           self.params_dict['delivery_list'],
                                                           self.params_dict['year_list']):
                # Fetch star and end date of periods
                del_start, del_end = self.get_start_end_product_date(product, delivery, year)
                del_start_list.append(del_start)
                del_end_list.append(del_end)
                data_name = market + '_' + product + '_' + str(year) + '_' + delivery
                fcst_nominal_list.append(nominal_dict[data_name].mean())
                fcst_ghr_list.append(ghr_dict[data_name].mean())
            
            self.processed_fcst_dict['nominal'][model] = pd.DataFrame([params_list for _,params_list in self.params_dict.items()
                                                             if type(params_list)==list] +\
                                                                      [fcst_nominal_list] +\
                                                                      [del_start_list]+\
                                                                          [del_end_list],
                                                            index=[a for a in list(self.params_dict)
                                                                   if 'list' in a]+['fcst_nominal',
                                                                                    'del_start',
                                                                                    'del_end']).T
            self.processed_fcst_dict['ghr'][model] = pd.DataFrame([params_list for _,params_list in self.params_dict.items()
                                                             if type(params_list)==list] +\
                                                                  [fcst_ghr_list]  +\
                                                                  [del_start_list]+\
                                                                      [del_end_list],
                                                            index=[a for a in list(self.params_dict)
                                                                   if 'list' in a]+['fcst_ghr',
                                                                                    'del_start',
                                                                                    'del_end']).T
            
    def create_fcst_curves(self, train_dict,
                             model_params_dict,
                             markets_to_fit='all',
                             curve_type='nominal'):
        if not hasattr(self, 'processed_fcst_dict'):
            self.get_processed_forecast(train_dict,model_params_dict,markets_to_fit)
        
        
        if curve_type in ['nominal']:
            curves_dict = self.processed_fcst_dict['nominal']
            fcst_name = 'fcst_nominal'
        else:
            curves_dict = self.processed_fcst_dict['ghr']
            fcst_name = 'fcst_ghr'
            
        curves_dfs_dict = {}
        tot_curves_dfs_dict = {}
        for model, curves_df in curves_dict.items():
            curves_dfs_dict[model] = {}

            delivery_df = pd.DataFrame()
            for delivery in np.unique(curves_df['delivery_list']):
                delivery_aux = curves_df.loc[curves_df['delivery_list']==delivery].copy()
                curves_dfs_dict[model][delivery] = {}
                
                for market in np.unique(delivery_aux['market_list']):
                    market_aux = delivery_aux.loc[delivery_aux['market_list']==market].copy()
                    try:
                        unique_periods = np.unique([re.sub('[^a-zA-Z]', '', a)
                                                    for a in market_aux['product_list']])
                    except:
                        print('831')
                    
                    market_df = pd.DataFrame()
                    for period in ['D', 'Wknd', 'W', 'M', 'Q', 'Y']:

                        if period in unique_periods:
                            mask = market_aux['product_list'].str.contains(period, na=False)
                            period_df = market_aux[mask][['product_list',
                                                          'year_list',
                                                         'del_start',
                                                         fcst_name]].copy()
                            period_df.set_index(['product_list',
                                                 'year_list',
                                                  'del_start'], inplace=True)
                            # period_df.sort_values('del_start', inplace=True)
                            # period_df.drop(['del_start'],axis=1,inplace=True)
                            period_df.columns = [market]
                            if market_df.empty:
                                market_df = period_df.copy()
                            else:
                                market_df = pd.concat([market_df, period_df])
                                
                        
                    

                    if delivery_df.empty:
                        delivery_df = market_df.copy()
                    else:
                        # delievery_df = pd.concat([delivery_df, market_df],
                        #                          axis=1,join='outer')
                        delivery_df = delivery_df.merge(market_df,
                                                        left_index=True,
                                                        right_index=True,how='outer')
                    
                curves_dfs_dict[model][delivery] = delivery_df
        return curves_dfs_dict
    
    
    def get_future_week_number(self, weeks_ahead):
        # Calculate the future date by adding the specified number of weeks to the current date
        future_date = self.pivot_date + timedelta(weeks=weeks_ahead)
        # Return the ISO week number of the future date
        return future_date.isocalendar()[1]
    
    
    def transform_params_dict(self, pivot):
        base_dict = self.original_params_dict.copy()
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
        if hasattr(self, 'fcst_data'):
            del self.fcst_data
        if hasattr(self, 'fcst_dict'):
            del self.fcst_dict
        if hasattr(self, 'fcst_model_data'):
            del self.fcst_model_data
        if hasattr(self, 'processed_fcst_dict'):
            del self.processed_fcst_dict
        for fcst_date in fcst_range:
            self.data_collection[fcst_date] = {}
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(fcst_date)
            self.update_params_dict(new_params_dict)
            

            da_data = self.assemble_da_data()
            train_dict = self.create_train_data(da_data)
            if nominal:
                tot_curves_dict[fcst_date] = self.create_fcst_curves(train_dict,
                                                          model_params_dict)
            else:
                tot_curves_dict[fcst_date] = self.create_fcst_curves(train_dict,
                                                          model_params_dict,
                                                          curve_type='ghr')
            if hasattr(self, 'fcst_data'):
                self.data_collection[fcst_date]['fcst_data'] = self.fcst_data
                del self.fcst_data
            if hasattr(self, 'fcst_dict'):
                self.data_collection[fcst_date]['fcst_dict'] = self.fcst_dict
                del self.fcst_dict
            if hasattr(self, 'fcst_model_data'):
                self.data_collection[fcst_date]['fcst_model_data'] = self.fcst_model_data
                del self.fcst_model_data
            if hasattr(self, 'processed_fcst_dict'):
                self.data_collection[fcst_date]['processed_fcst_dict'] = self.processed_fcst_dict
                del self.processed_fcst_dict
            

            
        return tot_curves_dict
    
    
    def get_scenario_forecast(self,  fcst_range,
                              model_params_dict,
                              scenario_data_dict: dict == {},
                              nominal=True):
        scenario_curves_dict = {}
        self.data_collection = {}
        if hasattr(self, 'fcst_data'):
            del self.fcst_data
        if hasattr(self, 'fcst_dict'):
            del self.fcst_dict
        if hasattr(self, 'fcst_model_data'):
            del self.fcst_model_data
        if hasattr(self, 'processed_fcst_dict'):
            del self.processed_fcst_dict
        for fcst_date in fcst_range:
            scenario_curves_dict[fcst_date] = {}
            self.data_collection[fcst_date] = {}
            self.set_pivot_date(fcst_date)
            new_params_dict = self.transform_params_dict(fcst_date)
            self.update_params_dict(new_params_dict)
            

            da_data = self.assemble_da_data()
            train_dict = self.create_train_data(da_data) 
            self.assemble_fcst_predictors(train_dict)
            base_fcst_dict = copy.deepcopy(self.fcst_data)
            for fwd_day, fwd_day_dict in scenario_data_dict[fcst_date].items():
                
                self.data_collection[fcst_date][fwd_day] = {}
                scenario_curves_dict[fcst_date][fwd_day] = {}
                for scenario, scenario_df in fwd_day_dict.items(): 
                    self.fcst_data = copy.deepcopy(base_fcst_dict)
                    self.data_collection[fcst_date][fwd_day][scenario] = {}
                    for prod, fcst_data in self.fcst_data.items():
                        start_date = fcst_data.index[0]
                        end_date = fcst_data.index[-1]
                        scenario_aux = scenario_df[start_date:end_date].copy()
                        self.fcst_data[prod][scenario_aux.columns] = scenario_aux
                        rld_diff = (base_fcst_dict[prod][scenario_aux.columns]-
                                    self.fcst_data[prod][scenario_aux.columns])
                        for col in rld_diff.columns:
                            c = col.split('_')[0]
                            for av_col in self.fcst_data[prod].columns:
                                split_col = av_col.split('_')
                                if len(split_col) == 3:
                                    c_match = split_col[-1]
                                    if c_match == c:
                                        self.fcst_data[prod][av_col] -= rld_diff[col]
                        
                        
                    
                
                
                    if nominal:
                        scenario_curves_dict[fcst_date][fwd_day][scenario] = self.create_fcst_curves(train_dict,
                                                                  model_params_dict)
                    else:
                        scenario_curves_dict[fcst_date][fwd_day][scenario] = self.create_fcst_curves(train_dict,
                                                                  model_params_dict,
                                                                  curve_type='ghr')
                    if hasattr(self, 'fcst_dict'):
                        self.data_collection[fcst_date]['fcst_dict'] = self.fcst_dict
                        del self.fcst_dict
                    if hasattr(self, 'fcst_model_data'):
                        self.data_collection[fcst_date]['fcst_model_data'] = self.fcst_model_data
                        del self.fcst_model_data
                    if hasattr(self, 'processed_fcst_dict'):
                        self.data_collection[fcst_date]['processed_fcst_dict'] = self.processed_fcst_dict
                        del self.processed_fcst_dict
            if hasattr(self, 'fcst_data'):
                self.data_collection[fcst_date]['fcst_data'] = self.fcst_data
                del self.fcst_data
            
                
        return scenario_curves_dict
            
            
            
            
        

        
        
        
                
                        
                        
                            
        
                            
                
                    
                        
                        
                        
                
                
            
            
        
        
            
        
        
            
            
        
        
        
    
    
        
            
            
        
    
    
        
    
    
    


