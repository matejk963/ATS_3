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



class TradeIntensity:
    
    def __init__(self, trades, best_orders, orders=None):
        self._trades = trades
        self._best_orders = best_orders
        self._orders = orders
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
    def train_size(self):
        if self._train_size is None:
            raise ValueError('No train size set')
        else:
            return self._train_size
        
    def set_train_size(self, train_size):
        self._train_size = train_size
    
    def prepare_data(self):

        self._trades = self._trades.groupby(level=0).agg({
                            'price': 'mean',
                            'action': 'mean',
                            'broker_id': 'mean',
                            'volume': 'sum'
                        })
        

        self.data = pd.merge(self.trades.reset_index(), self.best_orders.reset_index(),
                             on='datetime', how='outer')
        self.data = self.data.sort_values('datetime')
        self.data['bidbestprice'] = self.data['bidbestprice'].fillna(method='ffill')
        self.data['askbestprice'] = self.data['askbestprice'].fillna(method='ffill')
        self.data['mid'] = self.data[['bidbestprice', 'askbestprice']].mean(axis=1)
        self.data = self.data.set_index('datetime')
        
        self.data['trade_side'] = np.where(self.data['mid'] > self.data['price'], 0, 1)
        # self.data = self.data.reset_index()
        # self.data['int_value'] = np.where(pd.notnull(self.data['price']), 1, 0)
        self.data['time_dif'] = self.data.index.to_series().diff().dt.total_seconds()
        
        # return self.data
    def set_conditions(self):
        if hasattr(self, 'data'):
            pass
        else:
            self.prepare_data()
        # Bid true value
        self.data['bid_trade'] = np.where(self.data['trade_side']==0.,
                                          np.where(pd.notnull(self.data['price']),1,0),0)
        # Ask true value
        self.data['ask_trade'] = np.where(self.data['trade_side']==1.,
                                          np.where(pd.notnull(self.data['price']),1,0),0)
        """
        There I need to set up proper wieghts for incomming information values (0,1)
        for trades the lower the time diff higher the weight
        for order updates (no trades) the lower the time diff the lower the weight
        !!higher the dt lower the new value weight!!
        """
        # Bid price diff
        
        self.data['bid_time_diff'] = np.where(((self.data['bid_trade']==1)),
                                          self.data['time_dif'],
                                          1/self.data['time_dif'])
        self.data['ask_time_diff'] = np.where(((self.data['ask_trade']==1)),
                                          self.data['time_dif'],
                                          1/self.data['time_dif'])
        
        
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
    
    @staticmethod
    def create_dict(df):
        aux_dict = {}
        aux_dict['trades'] = df[['price', 'bidbestprice', 'askbestprice']].copy()
        for ba in ['bid', 'ask']:
            aux = df[[ba +'_trade']].copy()
            start_time = aux.index[0]
            date = start_time.date()
            aux_dict[ba] = aux.loc[aux.index.date==
                                             date]
            aux_dict[ba+'_trade'] = aux_dict[ba].loc[aux_dict[ba][ba+'_trade']==1]
            aux_dict[ba+'_event_times'] = (aux_dict[ba+'_trade'].index
                                             - start_time).astype('timedelta64[ns]').astype('int64') / 1e9
            aux_dict[ba+'_event_times_grid'] = (aux_dict[ba].index
                                             - start_time).astype('timedelta64[ns]').astype('int64') / 1e9
            aux_dict[ba+'_empirical_mean'] = np.mean(aux_dict[ba+'_event_times'])
            aux_dict[ba+'_empirical_variance'] = np.var(aux_dict[ba+'_event_times'])
            aux_dict[ba+'_empirical_moments'] = [aux_dict[ba+'_empirical_mean'],
                                                   aux_dict[ba+'_empirical_variance']]
            
        return aux_dict
    
    def create_train_test_dict(self, train_size=0.8):
        if self.train_size is None:
            pass
        else:
            train_size = self.train_size
        test_size = 1-train_size
        df = self.data.copy()
        dates = np.unique(df.index.date)
        train_dates, test_dates = self.split_array_by_ratio(dates, 
                                                            [train_size,
                                                             test_size])
        self.train_dict = {}
        self.test_dict = {}
        for date in dates:
            aux = self.data[self.data.index.date==date].copy()
            if date in train_dates:
                self.train_dict[date] = self.create_dict(aux)
            elif date in test_dates:
                self.test_dict[date] = self.create_dict(aux)
                
        
        
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
    
    def estimate_params(self, initial_quess=[0.1,1,1]):
        
        bid_params = []
        ask_params = []
        initial_guess = [0.1, 1,1]
        if hasattr(self, 'train_dict'):
            pass
        else:            
            self.create_train_test_dict()
        for date, aux_dict in self.train_dict.items():            
            
            for ba in ['bid', 'ask']:
                results = minimize(self.objective_function,
                                   initial_guess,
                                   args=(aux_dict[ba+'_empirical_moments']))
                if ba in ['bid']:
                    bid_params.append(results.x)
                elif ba in ['ask']:
                    ask_params.append(results.x)
        self.bid_params_tot = np.mean(np.array(bid_params),axis=0)
        self.ask_params_tot = np.mean(np.array(ask_params),axis=0)
        
        
    def get_bull_bear_move(self, t=15):
        # Function to find the target row and compute the (1,0,-1) value
        
        def find_and_compute(timestamp, row, date):
            df = self.test_dict[date]['trades']
            if pd.notna(row['price']):
                start_time = timestamp.floor('S')
                end_time = start_time + timedelta(seconds=t)
                future_rows = df[(df.index > timestamp) & (df.index <= end_time)].copy()

                bb_now, ba_now = row['bidbestprice'], row['askbestprice']
                condition_met = False

                for future_time, future_row in future_rows.iterrows():
                    bb_future, ba_future, price_future = future_row['bidbestprice'], future_row['askbestprice'], future_row['price']

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
            self.test_dict[date]['trades']['bull_bear_result'] = [find_and_compute(ts, row, date) for ts, row in aux_dict['trades'].iterrows()]
        
    # Define the exponential kernel function
    @staticmethod
    def exp_kernel(t, alpha, beta):
        return alpha * np.exp(-beta * t)
    
    # Define the intensity function for the Hawkes process
    def hawkes_intensity(self, time, event_times, mu, alpha, beta):
        return mu + sum(self.exp_kernel(time - event_time, alpha, beta)
                        for event_time in event_times if event_time <= time)
    
    def calculate_intensities(self):
        if hasattr(self, 'bid_params_tot'):
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
            self.test_dict[date]['trades']['int_bid'] = [self.hawkes_intensity(t, aux_dict['bid_event_times'], 0,
                                                self.bid_params_tot[0],
                                                self.bid_params_tot[1]) for t in 
                               aux_dict['bid_event_times_grid']]
            self.test_dict[date]['trades']['int_ask'] = [self.hawkes_intensity(t, aux_dict['ask_event_times'], 0,
                                                self.ask_params_tot[0],
                                                self.ask_params_tot[1]) for t in
                               aux_dict['ask_event_times_grid']]
        
        
        
    
    
    
    
    
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
