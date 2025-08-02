# -*- coding: utf-8 -*-
"""
Created on Tue Nov 21 13:00:12 2023

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from Math.accumfeatures import MSTD, MA, EMA
from Math.lm_class import kalman
import json

from scipy.integrate import odeint
from scipy.optimize import minimize


class ModelClass():
    __metaclass__ = abc.ABCMeta

    def __init__(self, model_name, weight, burn):
        self.name = model_name
        self.weight = weight
        self._burn = burn

    @abc.abstractmethod
    def fit(self, X):
        raise "not implemented"
        pass

    @abc.abstractmethod    
    def predict(self, X):
        pass

    @abc.abstractmethod
    def score(self, X, y, sample_weight=None):
        raise "not implemented"
        pass

# Constants
BID_ = True
ASK_ = False

class Iceberg():
    def __init__(self, level, volume):
        self.level = level
        self.volume = volume
        self.active = True
    
    def __dict__(self):
        return {'level': self.level,
                'volume': self.volume,
                'active': self.active}
    @classmethod
    def empty(cls):
        o = cls.__new__(cls)
        o.level = np.nan
        o.volume = np.nan
        o.active = False
        return o
    


class HawkesIntensity(ModelClass):
    def __init__(self, trades, best_orders, products):
        self._trades = trades
        self._best_orders = best_orders
        self._products = products
        self._train_size = None
        self._bid_event_times = None
        self._ask_event_times = None
        
    @property
    def trades(self):
        return self._trades
    @trades.setter
    def trades(self, value):
        self._trades = value
    @property
    def best_orders(self):
        return self._best_orders
    @property
    def orders(self):
        return self._orders
    @property
    def products(self):
        return self._products
    @property
    def bid_event_times(self):
        if self._bid_event_times is not None:
            return self._bid_event_times
        else:
            raise ValueError('Event times not set')
            
    @property
    def ask_event_times(self):
        if self._ask_event_times is not None:
            return self._ask_event_times
        else:
            raise ValueError('Event times not set')
            
    
    
    def update_event_times(self, event_times, ba):
        if ba in ['bid']:
            self._bid_event_times = event_times
        elif ba in ['ask']:
            self._ask_event_times = event_times
            
    def return_data_dict(self):
        if not hasattr(self, 'data'):
            self.prepare_data()
        data_dict = {}
        for prod in self.products:
            new_cols = [col for col in self.data.columns if prod in col]
            aux = self.data[new_cols]
            aux.columns = [col.replace('_' + prod, '') for col in aux.columns]
            if 'datetime' not in aux.columns:
                aux.index.name='datetime'
                aux.reset_index(inplace=True)
            aux = aux.rename(columns={'price': 'trd_price',
                                      'volume': 'volume',
                                      'bidbestprice': 'bid_price',
                                      'askbestprice': 'ask_price',
                                      'mid': 'mid_price',
                                      'trade_side': 'trd_side'})
            data_dict[prod] = aux
        return data_dict
    
    def prepare_data(self):
        self.data = pd.merge(self.trades.reset_index(), self.best_orders.reset_index(), on='datetime', how='outer')
        self.data = self.data.sort_values('datetime')
        self.data = self.data.set_index('datetime')
        for product in self.products:
            
            self.data[f'bidbestprice_{product}'] = self.data[f'bidbestprice_{product}'].fillna(method='ffill')
            self.data[f'askbestprice_{product}'] = self.data[f'askbestprice_{product}'].fillna(method='ffill')
            self.data[f'mid_{product}'] = self.data[[f'bidbestprice_{product}', f'askbestprice_{product}']].mean(axis=1)
            
            
            self.data[f'trade_side_{product}'] = np.select([self.data[f'price_{product}'].isna(),
                                                         self.data[f'price_{product}'] > self.data[f'mid_{product}'],
                                                         self.data[f'price_{product}'] < self.data[f'mid_{product}']],
                                                        [np.nan, 1, -1], default=np.nan)
            # np.where(self.data[f'price_{product}'] is not None,
            #                                               np.where(self.data[f'mid_{product}'] > self.data[f'price_{product}'], -1, np.nan), 1)
            self.data[f'time_dif_{product}'] = self.data.index.to_series().diff().dt.total_seconds()
        
    def set_conditions(self):
        if hasattr(self, 'data'):
            pass
        else:
            self.prepare_data()
        for product in self.products:
            # Bid true value
            self.data[f'bid_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==-1.,
                                              np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
            # Ask true value
            self.data[f'ask_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==1.,
                                              np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
            
            # Bid price diff
            self.data[f'bid_time_diff_{product}'] = np.where((self.data[f'bid_trade_{product}']==1),
                                              self.data[f'time_dif_{product}'],
                                              1/self.data[f'time_dif_{product}'])
            self.data[f'ask_time_diff_{product}'] = np.where((self.data[f'ask_trade_{product}']==1),
                                              self.data[f'time_dif_{product}'],
                                              1/self.data[f'time_dif_{product}'])
            
            
            

    # Create final dictionary with model parameters
    def create_dict(self, df):
        aux_dict = {}
        for product in self.products:
            aux_dict[product] = {}
            aux_dict[product]['trades'] = df[[f'price_{product}',
                                              f'bidbestprice_{product}',
                                              f'askbestprice_{product}']].copy()
            # for product in self.products:
            for ba in ['bid', 'ask']:
                # Corrected to use f-strings for dynamic column naming
                trade_col = f'{ba}_trade_{product}'
                aux = df[[trade_col]].copy()
                start_time = aux.index[0]
                date = start_time.date()
                if product not in aux_dict:
                    aux_dict[product] = {}
                aux_dict[product][ba] = aux.loc[aux.index.date == date]
                
                # Correct the key to use the formatted string
                trade_key = f'{ba}_trade_{product}'
                event_times_key = f'{ba}_event_times_{product}'
                event_times_grid_key = f'{ba}_event_times_grid_{product}'
                empirical_mean_key = f'{ba}_empirical_mean_{product}'
                empirical_variance_key = f'{ba}_empirical_variance_{product}'
                empirical_moments_key = f'{ba}_empirical_moments_{product}'
        
                aux_dict[product][trade_key] = aux_dict[product][ba].loc[aux_dict[product][ba][trade_col] == 1]
                
                # Calculate event times and add to dictionary
                aux_dict[product][event_times_key] = (aux_dict[product][trade_key].index - start_time).total_seconds()
                
                # Calculate event times grid and add to dictionary
                aux_dict[product][event_times_grid_key] = (aux_dict[product][ba].index - start_time).total_seconds()
                
                # Calculate empirical mean and variance and add to dictionary
                aux_dict[product][empirical_mean_key] = np.mean(aux_dict[product][event_times_key])
                aux_dict[product][empirical_variance_key] = np.var(aux_dict[product][event_times_key])
                
                # Store empirical moments in a list
                aux_dict[product][empirical_moments_key] = [aux_dict[product][empirical_mean_key], aux_dict[product][empirical_variance_key]]

            
        return aux_dict
    
    def create_train_test_dict(self, train_lookback=14):
        # Get data to df and set pivotal dates
        df = self.data.copy()
        start_date = pd.to_datetime(df.index.min().date())
        end_date = pd.to_datetime(df.index.max().date())
        window_end_date = start_date + pd.Timedelta(days=train_lookback)
        # Initiate major dictionary with rolling period and fill it with list 
        # of data dictionaries (test, train){'test_date': [test_data_dict,
        #                                                   train_data_dict]}
        self.major_dict = {}
        while window_end_date<=end_date:
            aux_df = df[start_date:window_end_date].copy()
            train_df = aux_df[:(window_end_date)-timedelta(days=1)].copy()
            test_df = aux_df[(window_end_date)-timedelta(days=1):].copy()
            if len(test_df)==0:
                window_end_date += pd.Timedelta(days=1)
                continue
            test_dict = self.create_dict(test_df)
            train_dict = self.create_dict(train_df)
            self.major_dict[window_end_date] = [train_dict, test_dict]
            window_end_date += pd.Timedelta(days=1)
        
                
        
        
    """
    Estimation of hawkes process paramteres
    
    Estimation is based on minimizing difference between theoretical moments (mean, variance)
    of the time ditribution between events
    """
    @staticmethod
    def objective_function(params, empirical_moments):
        def calculate_theoretical_moments(alpha, beta,
                                          lambda_infinity, t_max,
                                          initial_conditions):
            def system_of_odes(y, t):
                E_Nt, E_lambda_t = y
                dE_Nt_dt = E_lambda_t
                dE_lambda_t_dt = beta * (lambda_infinity - E_lambda_t) + alpha * E_lambda_t
                return [dE_Nt_dt, dE_lambda_t_dt]
    
            t = np.linspace(0, t_max, 100)
            sol = odeint(system_of_odes, initial_conditions, t)
            E_Nt = sol[:, 0]
            E_lambda_t = sol[:, 1]
    
            theoretical_mean = E_Nt[-1]
            theoretical_variance = E_lambda_t[-1]
    
            return theoretical_mean, theoretical_variance
        alpha, beta, lambda_infinity = params
        theoretical_moments = calculate_theoretical_moments(alpha, beta, lambda_infinity, t_max=10, initial_conditions=[0, 0])
        squared_error = sum((empirical_moment - theoretical_moment) ** 2 for empirical_moment, theoretical_moment in zip(empirical_moments, theoretical_moments))
        return squared_error
    
    """
    Function to estimate bid ask intensity distribution parameters
    Parameters are stored in dictionary in the following form:
        self.params_dict{'date': {'product': {'bid_params':[list of bid int distribution parameters],
                                              'ask_params': [list of ask int distribution parameters]}}}
        date: datetime, date of test data, parameters are estimated on data from <date-train_lookback:date)
        product: product that params are estiamted for. There can be multiple products for parameters estimation
        bid_params: key for actial list of parameters that consitutes mu, alpha, beta (base, excitement param, decay param)
        
    """
    
    def estimate_params(self, train_lookback=14, initial_guess=[2,1,1]):
        
        bid_params = []
        ask_params = []
        # initial_guess = [0.1, 1,1]
        if hasattr(self, 'major_dict'):
            pass
        else:
            self.prepare_data()
            self.set_conditions()
            self.create_train_test_dict(train_lookback)
        self.params_dict = {}
        
        for date, dict_list in self.major_dict.items():
            aux_dict = dict_list[0]
            self.params_dict[date] = {}
            for product in self.products:
                bid_params = []
                ask_params = []
                self.params_dict[date][product] = {}
                prod_dict = aux_dict[product]
            
                for ba in ['bid', 'ask']:
                    results = minimize(self.objective_function,
                                       initial_guess,
                                       args=(prod_dict[f'{ba}_empirical_moments_{product}']))
                    if ba in ['bid']:
                        bid_params.append(results.x)
                        self.params_dict[date][product]['bid_params'] = np.mean(np.array(bid_params),axis=0)
                    elif ba in ['ask']:
                        ask_params.append(results.x)
                        self.params_dict[date][product]['ask_params'] = np.mean(np.array(ask_params),axis=0)
    # Define the exponential kernel function
    @staticmethod
    def exp_kernel(t, alpha, beta):
        return alpha * np.exp(-beta * t)
    
    # Define the intensity function for the Hawkes process
    def hawkes_intensity(self, time, mu, alpha, beta, ba):
        if ba in ['bid']:
            return mu + sum(self.exp_kernel((time - event_time).total_seconds(), alpha, beta)
                            for event_time in self.bid_event_times if event_time <= time)
        elif ba in ['ask']:
            return mu + sum(self.exp_kernel((time - event_time).total_seconds(), alpha, beta)
                            for event_time in self.ask_event_times if event_time <= time)
    
    
    
        
