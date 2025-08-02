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
from .support_functions import calculate_MACD, calculate_lead_lag_triggers, calculate_regression_model_price, calc_vol_intensity_index, calculate_rolling_macd_fast

tol = 1e-6
trade_type_ll = {'open': 'AGG', 'close': 'AGG', 'trigg': 'AGG'}


class BacktestLL(BacktestClass):
    def __init__(self, volm_class, trade_type=trade_type_ll):
        super().__init__(volm_class, trade_type)
        price_list = ['timestamp', 'mid_price', 'bid_price', 'ask_price',
                      'trd_price', 'trd_side']
        self.prices_dict = {k: [] for k in price_list}


    def simulate_strategy(self, strategy_class, instr, df_lag, df_trades):
        # Simulate strategy defined by strategy class
        # Prepare data
        df_lag = df_lag.reset_index(drop=True)
        #df_lead = df_lead[['datetime', 'trd_price', 'trd_side']].dropna().reset_index(drop=True)

        df_lag['timestamp']=df_lag['datetime']

        df_lag = calculate_MACD(df_lag, 6, 14)
        df_lag = calculate_MACD(df_lag, 12, 26)
        df_lag = calculate_MACD(df_lag, 18, 38)
        df_lag = calculate_MACD(df_lag, 30, 60)


        df_lag['tag'] = 'lag'

        if 'level_0' in df_lag.columns:
            del df_lag['level_0']

        df_lag = df_lag.sort_values('datetime').reset_index()

        del df_lag['level_0'], df_lag['index']

        # Convert the timestamp to date and set it as a separate column if not already done
        df_lag['date'] = df_lag['datetime'].dt.date

        df_lag = calc_vol_intensity_index(df_lag, 3, 'lag')
        df_lag = calc_vol_intensity_index(df_lag, 5, 'lag')
        df_lag = calc_vol_intensity_index(df_lag, 10, 'lag')

        # Forward fill within each day
        df_lag['bid_price'] = df_lag.groupby('date')['bid_price'].ffill()
        df_lag['ask_price'] = df_lag.groupby('date')['ask_price'].ffill()
        df_lag['mid_price'] = df_lag.groupby('date')['mid_price'].ffill()
        df_lag['MACD_6_14'] = df_lag.groupby('date')['MACD_6_14'].ffill()
        df_lag['MACD_12_26'] = df_lag.groupby('date')['MACD_12_26'].ffill()
        df_lag['MACD_18_38'] = df_lag.groupby('date')['MACD_18_38'].ffill()
        df_lag['MACD_30_60'] = df_lag.groupby('date')['MACD_30_60'].ffill()

        df_lag['bid_macd'], df_lag['bid_volatility'] = calculate_rolling_macd_fast(df_lag, 'bid_price')
        df_lag['ask_macd'], df_lag['ask_volatility'] = calculate_rolling_macd_fast(df_lag, 'ask_price')

        df_lag = df_lag.dropna(subset=['bid_price', 'ask_price', 'mid_price'])

        df_lag['ba_spread']=df_lag['ask_price']-df_lag['bid_price']

        #adding trades for opening samples

        # Ensure data is sorted

        df1 = df_lag.sort_values('datetime')
        df2 = df_trades[['datetime']].sort_values('datetime')

        # Perform asof merge to get the latest available values from df1
        df2_filled = pd.merge_asof(df2, df1.drop(columns=['tag']), on='datetime', direction='backward')
        df2_filled['tag'] = 'trades'

        # Combine original df1 and new df2_filled
        df_combined = pd.concat([df1, df2_filled]).sort_values('datetime')


        #df_lag.to_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_jan_feb_enriched.csv')

        ###################################################################################################################
        ###

        price_dict = df_combined.to_dict('list')
        price_dict['datetime'] = pd.to_datetime(price_dict['datetime'])
        if 'timestamp' not in price_dict.keys():
            price_dict['timestamp'] = price_dict['datetime']
        price_dict.pop('index', None)
        del df_lag
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
                                                self.volm_class, self.trade_type)
            if not price or np.isnan(price):
                price=0


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

