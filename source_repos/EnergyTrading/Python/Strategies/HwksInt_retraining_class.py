# -*- coding: utf-8 -*-
"""
Created on Fri Jan  5 13:12:42 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, time
import datetime as dt
import warnings
import seaborn as sns
from Database.TPData import TPDataAssembly as TDA
from Strategies.IceBergOrders_class import IceBergOrders as IBO
# from Math.accumfeatures import EMA
from lifetimes.datasets import load_transaction_data
from lifetimes.utils import summary_data_from_transaction_data
from lifetimes.utils import calibration_and_holdout_data
from lifetimes import BetaGeoFitter

from scipy.integrate import odeint
from scipy.optimize import minimize



class MultiTradeIntensity:
    
    def __init__(self, trades, best_orders, products, orders=None):
        self._trades = trades
        self._best_orders = best_orders
        self._orders = orders
        self._products = products
        self._train_size = None
        
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
    def train_size(self):
        if self._train_size is None:
            raise ValueError('No train size set')
        else:
            return self._train_size
        
    def set_train_size(self, train_size):
        self._train_size = train_size
    
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

        
        
    @staticmethod
    def split_array_by_ratio(arr, ratios):
        """
        Splits a NumPy array into multiple parts based on given ratios.
    
        Parameters:
        arr (numpy.ndarray): The array to split.
        ratios (list): A list of ratios. Sum of all ratios should be 1.
    
        Returns:
        list: A list of numpy arrays split by the given ratios.
        """
        # Ensure the sum of ratios is approximately 1
        if not np.isclose(sum(ratios), 1):
            raise ValueError("Sum of ratios must be 1")
    
        # Calculate the cumulative sum of ratios and multiply by the length of the array
        # to get the split indices
        splits = np.cumsum([int(r * len(arr)) for r in ratios[:-1]])
    
        return np.split(arr, splits)
    
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
        
                
                
        
        
    def get_bull_bear_move(self, t=15):
        # Function to find the target row and compute the (1,0,-1) value
        
        def find_and_compute(timestamp, row, date, product):
            df = self.test_dict[date][product]['trades']
            price_key = f'price_{product}'
            bidbestprice_key = f'bidbestprice_{product}'
            askbestprice_key = f'askbestprice_{product}'
            if pd.notna(row[price_key]):
                start_time = timestamp.floor('S')
                end_time = start_time + timedelta(seconds=t)
                future_rows = df[(df.index > timestamp) & (df.index <= end_time)].copy()

                bb_now, ba_now = row[bidbestprice_key], row[askbestprice_key]
                condition_met = False

                for future_time, future_row in future_rows.iterrows():
                    bb_future, ba_future, price_future = future_row[bidbestprice_key], future_row[askbestprice_key], future_row[price_key]

                    if bb_future > ba_now or (pd.notna(price_future) and price_future > ba_now):
                        return 1
                    if ba_future < bb_now or (pd.notna(price_future) and price_future < bb_now):
                        return -1
                    condition_met = True

                return 0 if condition_met else None
            else:
                return None
            
        if hasattr(self, 'train_dict'):
            pass
        else:            
            self.create_train_test_dict()
        
        for date,aux_dict in self.test_dict.items():
            for product in self.products:
                self.test_dict[date][product]['trades'][f'bull_bear_result_{product}'] = [find_and_compute(ts, row, date, product)
                                                                               for ts, row in
                                                                               aux_dict[product]['trades'].iterrows()]
        
    # Define the exponential kernel function
    @staticmethod
    def exp_kernel(t, alpha, beta):
        return alpha * np.exp(-beta * t)
    
    # Define the intensity function for the Hawkes process
    def hawkes_intensity(self, time, event_times, mu, alpha, beta):
        return mu + sum(self.exp_kernel(time - event_time, alpha, beta)
                        for event_time in event_times if event_time <= time)
    
    def calculate_intensities(self):
        if hasattr(self, 'prams_dict'):
            pass
        else:
            warnings.warn('Parameters estimated with initial guess [0.1,1,1]', UserWarning)
            self.estimate_params()
        if hasattr(self, 'train_dict'):
            pass
        else:            
            self.create_train_test_dict()
        self.get_bull_bear_move()
            
        for date, aux_dict in self.test_dict.items():
            for product in self.products:
                prod_dict = aux_dict[product]
                for ba in ['bid', 'ask']:
                    int_key = f'int_{ba}_{product}'
                    params_key = f'{ba}_params'
                    event_times_key = f'{ba}_event_times_{product}'
                    event_times_grid_key = f'{ba}_event_times_grid_{product}'
                    self.test_dict[date][product]['trades'][int_key] = [self.hawkes_intensity(t, prod_dict[event_times_key], 0,
                                                        self.params_dict[product][params_key][0],
                                                        self.params_dict[product][params_key][1]) for t in 
                                       prod_dict[event_times_grid_key]]
                
        
        
        
    
    
    
    
    
    # def ema_int(self, tau):
    #     if hasattr(self, 'data'):
    #         pass
    #     else:
    #         self.prepare_data()
    #     self.set_conditions()
        
    #     ema_bid = EMA(tau)
    #     ema_ask = EMA(tau)
        
    #     self.data = self.data.iloc[1:].copy()
    #     self.data['bid_int'] = self.data.apply(lambda row: ema_bid.push(row['bid_trade'],
    #                                                                     row['bid_time_diff']),
    #                                             axis=1)
    #     self.data['ask_int'] = self.data.apply(lambda row: ema_bid.push(row['ask_trade'],
    #                                                                     row['ask_time_diff']),
    #                                             axis=1)
    #     # self.data['bid_int'] = self.data['bid_obj'].apply(lambda obj: obj.value)
        

            
        
        
        
        
def adjust_datetime_precision(df, datetime_col, floor):
    """
    Adjusts datetime precision in a dataframe without modifying the original dataframe.

    Parameters:
    df (pandas.DataFrame): The dataframe containing the datetime data.
    datetime_col (str): The name of the column containing datetime objects.

    Returns:
    pandas.DataFrame: A new dataframe with an additional column 'modified_datetime'.
    """

    # Create a copy of the dataframe to avoid modifying the original
    df_copy = df.copy()
    origin_cols = df_copy.columns

    # Ensure the datetime column is in the correct format
    df_copy[datetime_col] = pd.to_datetime(df_copy[datetime_col])

    # Round down to nearest second and count occurrences
    df_copy['datetime_rounded'] = df_copy[datetime_col].dt.floor(floor)
    df_copy['count_within_second'] = df_copy.groupby('datetime_rounded').cumcount()

    # Calculate the total occurrences of each second
    total_counts = df_copy['datetime_rounded'].map(df_copy['datetime_rounded'].value_counts())

    # Calculate the fraction to add
    df_copy['fraction_to_add'] = df_copy['count_within_second'] / total_counts

    # Add the fraction of a second to the rounded datetime
    df_copy['modified_datetime'] = df_copy['datetime_rounded'] + pd.to_timedelta(df_copy['fraction_to_add'], unit='s')


    
    df_copy['datetime'] = df_copy['modified_datetime']
    df_copy = df_copy[origin_cols].copy()
    
    return df_copy
    
    
# if __name__=='__main__':
    
    assembler = TDA(source='database')
    params_dict = {}
    params_dict['mkt_list'] = ['de']
    params_dict['tenor_list'] = ['m']
    params_dict['tn1_list'] = [1]
    params_dict['tn2_list'] = []
    params_dict['prod'] = 'base'
    params_dict['venue_list'] = ['eex']
    params_dict['start_date'] = datetime(2023, 11, 20)
    params_dict['end_date'] = datetime(2023, 11, 20)
    params_dict['ns'] = 2
    
    assembler = TDA(source='trayport')
    # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
    trades_dict = assembler.get_data(params_dict, target_data='trades')
    trades_key = next(iter(trades_dict))
    trades = trades_dict[trades_key]
    trades = trades.loc[trades['broker_id']==14].copy()
    assembler.set_data_source('database')
    ba_dict = assembler.get_data(params_dict, target_data='best_orders')
    ba_key = next(iter(ba_dict))
    assert ba_key == trades_key, 'Not the same instruments'
    
    
    int_inst = TradeIntensity(trades, ba_dict[ba_key])
    # trans_data = int_inst.prepare_data().sort_values('datetime')
    tau = 1
    int_inst.ema_int(tau)
    
    test_df = int_inst.data
    
    # test_df[['bid_int', 'ask_int']].plot()
    # plt.title('Tau ' + str(tau))
    # plt.show()
    
    ret_df = test_df.dropna().copy()
    ret_df['ret'] = ret_df['price'].diff()
    ret_df['cum_bid_int'] = ret_df['bid_int'].cumsum()
    ret_df['cum_ask_int'] = ret_df['ask_int'].cumsum()
    ret_df['cum_int'] = ret_df['cum_ask_int'] - ret_df['cum_bid_int']
    ret_df['cum_ret'] = ret_df['ret'].cumsum()
    # sns.regplot(data=ret_df.dropna(),x='ask_int', y='ret')
    # plt.show()
    
    # fig, ax1 = plt.subplots()
    
    # ax1.plot(ret_df['price'], 'g-')
    # ax1.set_xlabel('datetime')
    # ax1.set_ylabel('price', color='g')
    
    # ax2 = ax1.twinx()
    # ax2.plot(ret_df['cum_int'], 'b-')
    # ax2.set_ylabel('cum_int', color='b')
    # plt.title('Tau: ' + str(tau))
    # plt.show()
    
    X_data = test_df['mid']
    
    
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
    # pd.concat([pd.Series(X_data.reshape(-1,)), pd.Series(mu_list)], axis=1).plot(ax=ax1)
    X_data.plot(ax=ax1)
    test_df[['bid_int', 'ask_int']].plot(ax=ax2)
     
    def on_xlims_change(event_ax):
        other_ax = ax2 if event_ax == ax1 else ax1
        other_ax.set_xlim(event_ax.get_xlim())
     
    ax1.callbacks.connect('xlim_changed', on_xlims_change)
     
    plt.show()
    
    
    bid_data = test_df[['bid_trade']].reset_index()
    transaction_data = load_transaction_data()
    

    
    
    def adjust_datetime_precision(df, datetime_col):
        """
        Adjusts datetime precision in a dataframe without modifying the original dataframe.
    
        Parameters:
        df (pandas.DataFrame): The dataframe containing the datetime data.
        datetime_col (str): The name of the column containing datetime objects.
    
        Returns:
        pandas.DataFrame: A new dataframe with an additional column 'modified_datetime'.
        """
    
        # Create a copy of the dataframe to avoid modifying the original
        df_copy = df.copy()
        origin_cols = df_copy.columns
    
        # Ensure the datetime column is in the correct format
        df_copy[datetime_col] = pd.to_datetime(df_copy[datetime_col])
    
        # Round down to nearest second and count occurrences
        df_copy['datetime_rounded'] = df_copy[datetime_col].dt.floor('S')
        df_copy['count_within_second'] = df_copy.groupby('datetime_rounded').cumcount()
    
        # Calculate the total occurrences of each second
        total_counts = df_copy['datetime_rounded'].map(df_copy['datetime_rounded'].value_counts())
    
        # Calculate the fraction to add
        df_copy['fraction_to_add'] = df_copy['count_within_second'] / total_counts
    
        # Add the fraction of a second to the rounded datetime
        df_copy['modified_datetime'] = df_copy['datetime_rounded'] + pd.to_timedelta(df_copy['fraction_to_add'], unit='s')
    

        
        df_copy['datetime'] = df_copy['modified_datetime']
        df_copy = df_copy[origin_cols].copy()
        
    
        return df_copy
    bid_trades = ret_df.loc[ret_df['bid_trade']==1]['bid_trade'].reset_index()
    bid_trades_adj = adjust_datetime_precision(bid_trades, 'datetime')
    # bid_trades_adj = bid_trades.copy()
    # bid_trades_adj['datetime'] = pd.to_datetime(bid_trades_adj['datetime'].dt.date)
    
    summary = summary_data_from_transaction_data(bid_trades_adj, 'bid_trade', 'datetime', freq='s')    
    summary['recency'] = summary['recency'] 
    summary['T'] = summary['T'] 
    
    bgf = BetaGeoFitter(penalizer_coef=0.8)
    
    trade = summary.iloc[[0]]
    # trade = summary.iloc[[1]]
    
    bgf.fit(trade['frequency'], trade['recency'], trade['T'])
    
    print(bgf)
    
    from lifetimes.plotting import plot_frequency_recency_matrix
    
    plot_frequency_recency_matrix(bgf)
    
    from lifetimes.utils import calibration_and_holdout_data

    summary_cal_holdout = calibration_and_holdout_data(bid_trades_adj, 'bid_trade', 'datetime', freq='s',
                                            calibration_period_end='2023-11-20 14:00:12' )

    from lifetimes.plotting import plot_calibration_purchases_vs_holdout_purchases

    bgf.fit(summary_cal_holdout['frequency_cal'], summary_cal_holdout['recency_cal'], summary_cal_holdout['T_cal'])
    plot_calibration_purchases_vs_holdout_purchases(bgf, summary_cal_holdout)

    bgf.fit(trade['frequency'], trade['recency'], trade['T'])

    from lifetimes.plotting import plot_history_alive    
    days_since_birth = 100
    sp_trans = bid_trades_adj.copy()
    sp_trans['datetime'] = sp_trans['datetime'].dt.floor('S')
    
    sp_trans = sp_trans.groupby(['datetime']).sum()
    sp_trans = sp_trans.reset_index()
    # sp_trans['datetime'] = sp_trans['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    plot_history_alive(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
