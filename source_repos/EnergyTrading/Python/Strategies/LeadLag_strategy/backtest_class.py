# -*- coding: utf-8 -*-
"""
Created on Thu Dec  7 17:37:56 2023

@author: Marek
"""

import numpy as np
import abc
import pandas as pd
from datetime import datetime, time

from Utilities.backtest_class import BacktestClass


tol = 1e-6
trade_type_ll = {'open': 'AGG', 'close': 'AGG', 'trigg': 'AGG'}


class BacktestLL(BacktestClass):
    def __init__(self, volm_class, trade_type=trade_type_ll):
        super().__init__(volm_class, trade_type)
        price_list = ['timestamp', 'mid_price', 'bid_price', 'ask_price',
                      'trd_price', 'trd_side']
        self.prices_dict = {k: [] for k in price_list}


    def simulate_strategy(self, strategy_class, instr, df_lag, df_lead):
        # Simulate strategy defined by strategy class
        # Prepare data
        df_lag = df_lag.reset_index(drop=True)
        df_lead = df_lead[['datetime', 'trd_price', 'trd_side']].dropna().reset_index(drop=True)

        df_lag['timestamp']=df_lag['datetime']
        df_lead['timestamp']=df_lead['datetime']

        ###calculate times when Lag market needs to be triggered according to Lead Market data
        max_secs_between_trades = strategy_class.param_dict['max_secs_between_trades']
        cluster_trade_num_threshold = strategy_class.param_dict['cluster_trade_num_threshold']
        min_price_movement = strategy_class.param_dict['min_price_movement']


        def calulate_MACD(df):
            # Extract date part from datetime for grouping
            df['date'] = df['datetime'].dt.date

            # Filtering the dataset to only include rows where trd_price is not null
            df_filtered = df.dropna(subset=['trd_price'])

            # Function to calculate MACD for each group
            def calculate_macd(group):
                short_ema = group['trd_price'].ewm(span=12, adjust=False).mean()
                long_ema = group['trd_price'].ewm(span=26, adjust=False).mean()
                group['MACD'] = short_ema - long_ema
                return group

            # Apply the MACD calculation to each group (each day)
            df_filtered = df_filtered.groupby('date').apply(calculate_macd)

            # Merging the results back into the original dataset
            df = df.merge(df_filtered[['datetime', 'MACD']], on='datetime', how='left')
            df['MACD'] = df.groupby('date')['MACD'].ffill()

            return df

        def analyze_clusters(df):
            df['time_diff'] = df['datetime'].diff().dt.total_seconds().fillna(0)

            results = []
            i = 0
            while i < len(df) - cluster_trade_num_threshold + 1:
                # Check if the next cluster_trade_num_threshold - 1 trades are within the time threshold
                valid_cluster = all(df.iloc[j]['time_diff'] <= max_secs_between_trades for j in
                                    range(i + 1, i + cluster_trade_num_threshold))

                if valid_cluster:
                    cluster_df = df.iloc[i:i + cluster_trade_num_threshold]
                    max_price = cluster_df['trd_price'].max()
                    min_price = cluster_df['trd_price'].min()
                    median_price = cluster_df['trd_price'].median()
                    price_movement = max_price - min_price
                    direction = 0
                    if price_movement > min_price_movement and median_price > min_price and median_price < max_price:
                        if cluster_df[cluster_df['trd_price'] == min_price].index[0] < \
                                cluster_df[cluster_df['trd_price'] == max_price].index[0]:
                            direction = 1
                        else:
                            direction = -1
                    results.append({
                        'start_index': i,
                        'end_index': i + cluster_trade_num_threshold-1,
                        'start_datetime': cluster_df['datetime'][i],
                        'end_datetime': cluster_df['datetime'][i + cluster_trade_num_threshold-1],
                        'price_movement': price_movement,
                        'direction': direction
                    })
                    # Skip to the trade after the current cluster
                    i += 1
                else:
                    i += 1

            return results

        df_lag_with_MACD=calulate_MACD(df_lag)
        results = pd.DataFrame(analyze_clusters(df_lead))
        trigger_df = results[results['direction'] != 0][['end_datetime', 'direction']].rename(
            columns={'end_datetime': 'trigger_datetime'}).reset_index(drop=True)


        ###

        price_dict = df_lag_with_MACD.to_dict('list')
        price_dict['datetime'] = pd.to_datetime(price_dict['datetime'])
        if 'timestamp' not in price_dict.keys():
            price_dict['timestamp'] = price_dict['datetime']
        price_dict.pop('index', None)
        del df_lag
        del df_lag_with_MACD
        # Reset class
        self.reset_time()
        self.nT = len(price_dict['timestamp'])

        # Run strategy on data
        aux_dict = {k: v[self.current_t] for k, v in price_dict.items()}
        self.prices_dict.update(aux_dict)
        while self.is_active:
            aux_dict = {k: v[self.current_t] for k, v in price_dict.items()}
            # Update price dict after night
            if aux_dict['timestamp'].date() != self.prices_dict['timestamp'].date():
                self.prices_dict.update(aux_dict)
            price, vol = strategy_class.process(aux_dict,
                                                self.volm_class, self.trade_type, trigger_df)
            vol = self.execute(strategy_class, vol)
            position = strategy_class.curr_position
            self.save_trade(aux_dict, price, vol, position)
            # Update last prices
            self.prices_dict.update(aux_dict)
            self.progress_time()
        return self.profit_series



    def cost_function(self, output_series, method):
        # Process output from calibration
        ret = np.diff(output_series.values, n=1)
        if method == 'avg':
            output_val = -np.mean(ret)
        elif method == 'std':
            output_val = np.std(ret)
        elif method == 'sharp':
            output_val = -np.mean(ret) / np.std(ret)
        else:
            ValueError('backtest_class: cost function unknown method :', method)
        return output_val
