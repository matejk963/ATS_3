# -*- coding: utf-8 -*-
"""
Created on Tue Nov 21 13:00:12 2023

@author: Marek
"""

import abc
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
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
            
            # Bid true value
            self.data[f'bid_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==-1.,
                                              np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
            # Ask true value
            self.data[f'ask_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==1.,
                                              np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
        
    def create_data_dict(self):
        if hasattr(self, 'data'):
            pass
        else:
            self.prepare_data()
        self.data_dict = {}
        for date in self.data.index.normalize().unique():
            aux = self.data[self.data.index.normalize()==date]
            self.data_dict[date] = self.create_dict(aux)
            
            
                
    
    # def set_conditions(self):
    #     if hasattr(self, 'data'):
    #         pass
    #     else:
    #         self.prepare_data()
    #     for product in self.products:
    #         # Bid true value
    #         self.data[f'bid_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==-1.,
    #                                           np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
    #         # Ask true value
    #         self.data[f'ask_trade_{product}'] = np.where(self.data[f'trade_side_{product}']==1.,
    #                                           np.where(pd.notnull(self.data[f'price_{product}']),1,0),0)
            
    #         # Bid price diff
    #         self.data[f'bid_time_diff_{product}'] = np.where((self.data[f'bid_trade_{product}']==1),
    #                                           self.data[f'time_dif_{product}'],
    #                                           1/self.data[f'time_dif_{product}'])
    #         self.data[f'ask_time_diff_{product}'] = np.where((self.data[f'ask_trade_{product}']==1),
    #                                           self.data[f'time_dif_{product}'],
    #                                           1/self.data[f'time_dif_{product}'])
            
            
      
              
          

    
    
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
                # Convert them to a pandas datetime series
                trade_times = pd.to_datetime(aux_dict[product][trade_key].index)
                trade_differences = trade_times.to_series().diff().dropna()
                trade_differences_seconds = trade_differences.dt.total_seconds()
                aux_dict[product][event_times_key] = trade_differences_seconds
                
                # Calculate event times grid and add to dictionary
                # aux_dict[product][event_times_grid_key] = (aux_dict[product][ba].index - start_time).total_seconds()
                
                # Calculate empirical mean and variance and add to dictionary
                aux_dict[product][empirical_mean_key] = np.mean(aux_dict[product][event_times_key])
                aux_dict[product][empirical_variance_key] = np.var(aux_dict[product][event_times_key])
                
                # Store empirical moments in a list
                aux_dict[product][empirical_moments_key] = [aux_dict[product][empirical_mean_key], aux_dict[product][empirical_variance_key]]

            
        return aux_dict
    
    # def create_train_test_dict(self, train_lookback=14):
    #     # Get data to df and set pivotal dates
    #     df = self.data.copy()
    #     start_date = pd.to_datetime(df.index.min().date())
    #     end_date = pd.to_datetime(df.index.max().date())
    #     window_end_date = start_date + pd.Timedelta(days=train_lookback)
    #     # Initiate major dictionary with rolling period and fill it with list 
    #     # of data dictionaries (test, train){'test_date': [test_data_dict,
    #     #                                                   train_data_dict]}
    #     self.major_dict = {}
    #     while window_end_date<=end_date:
    #         aux_df = df[start_date:window_end_date].copy()
    #         train_df = aux_df[:(window_end_date)-timedelta(days=1)].copy()
    #         test_df = aux_df[(window_end_date)-timedelta(days=1):].copy()
    #         if len(test_df)==0:
    #             window_end_date += pd.Timedelta(days=1)
    #             continue
    #         test_dict = self.create_dict(test_df)
    #         train_dict = self.create_dict(train_df)
    #         self.major_dict[window_end_date] = [train_dict, test_dict]
    #         window_end_date += pd.Timedelta(days=1)
            
     
        
                
        
        
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
    @staticmethod
    def hawkes_log_likelihood(params, event_times):
        mu, alpha, beta = params
        T = event_times[-1]
        n = len(event_times)
        
        # Intensity for each event
        intensity = mu + alpha * np.sum(np.exp(-beta * (event_times[-1] - event_times[:n])), axis=0)

        # Log-likelihood
        log_likelihood = n * np.log(mu) + np.sum(np.log(intensity))
        log_likelihood -= mu * T
        log_likelihood -= (alpha / beta) * (np.sum(1 - np.exp(-beta * (T - event_times))))
        
        # Return negative log-likelihood for minimization
        return -log_likelihood
    
    # Define the conditional intensity function for the Hawkes process
        
    # Define the log-likelihood function of the Hawkes process
    # @staticmethod
    # def negative_log_likelihood(params, data):
    #     def lambda_t(t, history, mu, alpha, beta):
    #         """Computes the conditional intensity of the Hawkes process at time t."""
    #         intensity = mu
    #         for t_i in history:
    #             if t_i < t:
    #                 intensity += alpha * np.exp(-beta * (t - t_i))
    #         return intensity
    #     """Computes the negative log-likelihood for the Hawkes process."""
    #     mu, alpha, beta = params
    #     if mu <= 0 or alpha <= 0 or beta <= 0:  # Check if parameters are positive
    #         return np.inf  # Return infinity if parameters are not valid
    
    #     likelihood = 0
    #     history = []
    #     for t in data:
    #         lambda_t_i = lambda_t(t, history, mu, alpha, beta)
    #         likelihood += np.log(lambda_t_i)
    #         history.append(t)
    #     likelihood -= mu * data[-1]  # Subtract the integral of the base rate
    #     for t_i in history:
    #         for t_j in history:
    #             if t_j > t_i:
    #                 likelihood -= alpha / beta * (1 - np.exp(-beta * (t_j - t_i)))
    #     return -likelihood  # Return negative log-likelihood
    
    @staticmethod
    def negative_log_likelihood(params, data):
        mu, alpha, beta = params
        if mu <= 0 or alpha <= 0 or beta <= 0:
            return np.inf  # Ensure parameters are positive

        # Convert data to numpy array for efficient computation
        data = np.array(data)

        # Initialize likelihood
        likelihood = 0

        # Calculate the contribution of each event to the likelihood
        for i, t in enumerate(data):
            # Compute sum of influences from all previous events
            # This avoids recomputing the exponential for all pairs of events
            prev_events = data[:i]  # Events before the current event
            time_diffs = t - prev_events  # Time differences to previous events
            intensity_contributions = alpha * np.exp(-beta * time_diffs)
            lambda_t = mu + np.sum(intensity_contributions)

            # Update the likelihood
            likelihood += np.log(lambda_t)

        # Subtract the integral of the base rate over the observation period
        likelihood -= mu * data[-1]

        # Subtract the integral of the triggered intensity
        # Instead of calculating for each pair, sum over all past event contributions
        # Note: The integral of each exponential term over the observation period
        for i, t in enumerate(data):
            # Only consider contributions from events that occurred before t
            if i > 0:
                prev_events = data[:i]
                time_diffs = t - prev_events
                likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

        # Add contribution from the last event to the end of the observation window
        last_event = data[-1]
        time_diffs = last_event - data[:-1]
        likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

        return -likelihood  # Return the negative log-likelihood
    
    
    @staticmethod
    def get_initial_guess(time_differences):
        # Sample time differences data
       time_differences = np.array([time_differences])  # Replace with your actual time differences

       # Estimating mu (base intensity)
       # We'll use the entire duration to estimate the baseline rate of events
       total_time = np.sum(time_differences)
       total_events = len(time_differences)
       mu_estimate = total_events / total_time  # Events per unit time

       # Estimating alpha and beta (excitation and decay parameters)
       # This is more heuristic-based and will need adjustment based on your data

       # For alpha, let's assume the immediate increase in event rate is proportional to the initial peak
       # This is heuristic and requires you to analyze the specific behaviors in your data
       peak_rate = np.max(np.histogram(time_differences, bins=50)[0]) / (total_time / 50)  # Peak event rate in one of the bins
       alpha_estimate = (peak_rate - mu_estimate)  # Increase over baseline, simplistic approach

       # For beta, we need to estimate how quickly the rate decays back to baseline
       # This is a simplified approach, assuming exponential decay back to the baseline after the peak
       # Find where the event rate falls back to approximately the baseline rate
       # This could be refined with more sophisticated analysis
       decay_time_index = np.argmax(np.histogram(time_differences, bins=50)[0] < mu_estimate * (total_time / 50))
       decay_time = (total_time / 50) * decay_time_index  # Approximate time it takes to decay to baseline

       beta_estimate = 1 / decay_time  # Assuming exponential decay, beta is the inverse of decay time
       return [mu_estimate, alpha_estimate, beta_estimate]
    
    def estimate_params(self, train_lookback=30, no_of_it=1):
        def index_of_nearest(lst, target):
            # Calculate the absolute differences
            differences = [abs(x - target) for x in lst]
            # Find the index of the smallest difference
            index_of_min = differences.index(min(differences))
            return index_of_min
                
        
        # initial_guess = [0.1, 1,1]
        if hasattr(self, 'data_dict'):
            pass
        else:
            self.create_data_dict()
        self.params_dict = {}
        
        prev_date = None
        bounds = [(0, None), (0, None), (0, None)]
        
        data_dict = self.data_dict
        
        start_date = list(data_dict)[0]
        start_month = start_date.month
        start_year = start_date.year
        end_date = list(data_dict)[-1]
        comp_date = start_date
        initial_params_dict = {}
        event_times_dict = {}
        
        while comp_date<=end_date:
            if comp_date == pd.Timestamp('20231204'):                print('stop')
            comp_month = comp_date.month
            comp_year = comp_date.year
            if ((comp_month == start_month)&(comp_year == start_year)):
                old_comp = comp_date
                comp_date += pd.Timedelta(1,'D')
            else:
                if comp_date not in list(data_dict):
                    old_comp = comp_date
                    comp_date += pd.Timedelta(1,unit='D')
                    continue
                comp_date_month_shift = comp_date - relativedelta(months=1)
                last_month = comp_date_month_shift.month
                last_year = comp_date_month_shift.year               
                
                self.params_dict[comp_date] = {}
                                
                comp_index = list(data_dict).index(comp_date)
            
                # Estimate parameters for each day
                
                keys_for_avg = [a for a in list(data_dict) if ((a.month == last_month)&(a.year==last_year))]
                keys_for_est = [list(data_dict)[comp_index]]
                
                
                
                
                if not len(event_times_dict) == 0:
                    if old_comp.month == comp_date.month:
                        data_collect_bool = False
                    else:
                        data_collect_bool = True
                        event_times_dict = {}
                        bid_params = {}
                        ask_params = {}
                else:
                    data_collect_bool = True
                    bid_params = {}
                    ask_params = {}
                    
                    
                for date, date_dict in data_dict.items():
                    if date in keys_for_avg:
                        
                        if not data_collect_bool:
                           continue
                        
                        for prod, prod_df in date_dict.items():
                            if prod not in event_times_dict:
                                event_times_dict[prod] = {}

                            
                            for ba in ['bid', 'ask']:
                                aux = prod_df[f'{ba}_event_times_dem1']
                                if ba not in event_times_dict[prod]:
                                    event_times_dict[prod][ba] = aux.copy()
                                else:
                                    event_times_dict[prod][ba] = pd.concat([event_times_dict[prod][ba], aux])
                        
                                
                    elif date in keys_for_est:
                        for prod,prod_dict in event_times_dict.items():
                            initial_params_dict[prod] = {}
                            for ba, ba_df in prod_dict.items():
                                initial_params_dict[prod][ba] = self.get_initial_guess(ba_df)
                    
                        
                        for prod, prod_dict in date_dict.items():
                            if prod not in bid_params:
                                bid_params[prod] = []
                                ask_params[prod] = []
                                for ba in ['bid', 'ask']:
                                    
                                    # aux = prod_dict[f'{ba}_event_times_dem1']
                                    aux = event_times_dict[prod][ba]
                                    if aux.shape[0] == 0:
                                        continue
                                    aux.index = aux.index.date
                                    # timestamps = aux.index
                                    initial_params = initial_params_dict[prod][ba]
                                    
                                    # Convert timestamp strings to datetime objects
                                    # datetime_objects = timestamps.copy()
                                    
                                    # Calculate time differences in seconds from the first event
                                    # event_times = np.array([(dt - datetime_objects[datetime_objects.date == dt.date][0]).total_seconds() for dt in datetime_objects])
                                    aux_group = aux.groupby(aux.index).cumsum()
                                    for opt_date in aux_group.index.drop_duplicates():
                                        results = minimize(self.negative_log_likelihood,
                                                                   initial_params,
                                                                   args=(np.array(aux_group[opt_date]),),
                                                                   bounds=bounds, method='L-BFGS-B',
                                                                   options={'gtol': 1e-6, 'ftol': 1e-6})
                                        # print(results.x)
                                        if results.success:
                                            if ba in ['bid']:
                                                bid_params[prod].append(results.x)
                                                
                                            elif ba in ['ask']:
                                                ask_params[prod].append(results.x)
                                            
                            self.params_dict[date][prod] = {}
                            self.params_dict[date][prod]['bid_params'] = np.nanmean(np.array(bid_params[prod]),axis=0)
                            self.params_dict[date][prod]['ask_params'] = np.nanmean(np.array(ask_params[prod]),axis=0)
                        
                                            
                    # elif date == comp_date:
                    #     for product in self.products:
                    #         self.params_dict[date][product] = {}
                    #         self.params_dict[date][product]['bid_params'] = np.nanmean(np.array(bid_params[product]),axis=0)
                    #         self.params_dict[date][product]['ask_params'] = np.nanmean(np.array(ask_params[product]),axis=0)
                    else:
                        
                        continue
                # old_bid_params = bid_params
                # old_ask_params = ask_params
                
            old_comp = comp_date
            comp_date += pd.Timedelta(1,unit='D')
                            
            
                
        
        # start_date = list(self.data_dict)[0]
        # end_date = list(self.data_dict)[1]
        
        # window_end_date = start_date + pd.Timedelta(days=train_lookback)
        # for product in self.products:
        #     while window_end_date<=end_date:
        #         date = window_end_date - pd.Timedelta(days=1)
        #         bid_params=[]
        #         ask_params=[]
        #         while date>=start_date:
        #             bid_params.append(self.params_dict[date][product]['bid_params'])
        #             ask_params.append(self.params_dict[date][product]['ask_params'])
        #             date -= pd.Timedelta(days=1)
        #         self.params_dict[window_end_date][product]['bid_params'] = np.nanmedian(np.array(bid_params),axis=0)
        #         self.params_dict[window_end_date][product]['ask_params'] = np.nanmedian(np.array(ask_params),axis=0)
                
                
        #         window_end_date += pd.Timedelta(days=1)
        #         start_date += pd.Timedelta(days=1)
        # start_date = list(self.data_dict)[0]
        # window_end_date = start_date + pd.Timedelta(days=train_lookback-1)
        # erase_dates_range = pd.date_range(start_date,end_date)
        # for date in erase_dates_range:
        #     if date in self.params_dict:
        #         del self.params_dict[date]
        
        
        
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
        
        
    # def compute_intensities(self, params_dict=None):
    #     if params_dict is None:
    #         self.estimate_params()
    #         params_dict = self.params_dict
    #     data = self.data.copy()
        
    #     first_date = list(params_dict)[0]
    #     data = data[first_date:].copy()
    #     int_dict = {}
    #     for date, date_dict in params_dict.items():
    #         aux_data = data.loc[data.index.date==date.date()].copy()
    #         for prod, prod_dict in date_dict.items():
    #             if prod not in int_dict:
    #                 int_dict[prod] = {}
    #                 int_dict[prod]['bid'] = []
    #                 int_dict[prod]['ask'] = []
    #                 int_dict[prod]['timestamp'] = []
    #             bid_params = prod_dict['bid_params']
    #             ask_params = prod_dict['ask_params']
    #             aux_df = aux_data[[a for a in aux_data.columns if prod in a]]
    #             aux_df.columns = [a.split('_')[0] for a in aux_df.columns]
    #             bid_event_times = []
    #             ask_event_times = []
    #             bid_int_list = []
    #             ask_int_list = []
                
    #             for i, row in aux_df.iterrows():
    #                 bid_int = np.nan
    #                 ask_int = np.nan
    #                 if np.isnan(row['price']):
    #                     if (len(bid_event_times)==0) and (len(ask_event_times)==0):
    #                         continue
    #                     if len(ask_event_times)!=0:
    #                         ask_int = self.hawkes_intensity(i, ask_params[0],
    #                                                         ask_params[1],
    #                                                         ask_params[2], 'ask')
    #                     if len(bid_event_times)!=0:
    #                         bid_int = self.hawkes_intensity(i, bid_params[0],
    #                                                         bid_params[1],
    #                                                         bid_params[2], 'bid')
    #                 else:
    #                     if row['trade'] == 1:
    #                         ask_event_times.append(i)
    #                         self.update_event_times(ask_event_times, 'ask')
    #                     elif row['trade'] == -1:
    #                         bid_event_times.append(i)
    #                         self.update_event_times(bid_event_times, 'bid')
                            
    #                     if len(ask_event_times)!=0:
    #                         ask_int = self.hawkes_intensity(i, ask_params[0],
    #                                                         ask_params[1],
    #                                                         ask_params[2], 'ask')
    #                     if len(bid_event_times)!=0:
    #                         bid_int = self.hawkes_intensity(i, bid_params[0],
    #                                                         bid_params[1],
    #                                                         bid_params[2], 'bid')
    #                 int_dict[prod]['bid'].append(bid_int)
    #                 int_dict[prod]['ask'].append(ask_int)
    #                 int_dict[prod]['timestamp'].append(row.name)
                    
    #     for prod in self.products:
    #         aux = pd.DataFrame({'datetime': int_dict[prod]['timestamp'],
    #                             'bid_int' + '_' + prod: int_dict[prod]['bid'],
    #                             'ask_int' + '_' + prod: int_dict[prod]['ask']})
    #         aux.set_index('datetime', inplace=True)
    #         aux.set_index.name = 
    #         self.data_with_int = self.data.merge(aux,left_index=True, right_index=True, how='left')
    #         self.data_with_int.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_data_with_int.csv')
                    
            
    
    
    
        
