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
from .support_functions import calculate_MACD, calculate_lead_lag_triggers, calculate_regression_model_price, calc_vol_intensity_index

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
        #df_lead = df_lead[['datetime', 'trd_price', 'trd_side']].dropna().reset_index(drop=True)

        df_lag['timestamp']=df_lag['datetime']
        df_lead['timestamp']=df_lead['datetime']


        df_lag = calculate_MACD(df_lag, 6, 14)
        df_lag = calculate_MACD(df_lag, 12, 26)
        df_lag = calculate_MACD(df_lag, 18, 38)
        df_lag = calculate_MACD(df_lag, 30, 60)

        df_lead = calculate_regression_model_price(df_lead, df_lag, 10, 10, 3, strategy_class.param_dict['fit_reg_coef'], strategy_class.param_dict['coef1'], strategy_class.param_dict['coef2'] )

        df_lag['tag'] = 'lag'
        df_lead['tag'] = 'lead'

        df_lag = pd.concat([df_lag, df_lead[
            ['datetime', 'timestamp', 'tag', 'trd_price', 'lag_price_predicted', 'lag_price_predicted_datetime',
             'lag_price_tick', 'coef1', 'coef2', 'lead_price_tick']].reset_index(drop=True)]).reset_index(
            drop=True).sort_values('datetime').reset_index()

        del df_lag['level_0'], df_lag['index']

        # Convert the timestamp to date and set it as a separate column if not already done
        df_lag['date'] = df_lag['datetime'].dt.date

        df_lag = calc_vol_intensity_index(df_lag, 3, 'lead')
        df_lag = calc_vol_intensity_index(df_lag, 5, 'lead')
        df_lag = calc_vol_intensity_index(df_lag, 10, 'lead')
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


        df_lag['VII_3_ratio'] = df_lag['VII_lead_3'] / df_lag['VII_lag_3'].replace(0, 1e-6)
        df_lag['VII_5_ratio'] = df_lag['VII_lead_5'] / df_lag['VII_lag_5'].replace(0, 1e-6)
        df_lag['VII_10_ratio'] = df_lag['VII_lead_10'] / df_lag['VII_lag_10'].replace(0, 1e-6)

        df_lag = df_lag.dropna(subset=['bid_price', 'ask_price', 'mid_price'])

        df_lag['ba_spread']=df_lag['ask_price']-df_lag['bid_price']

        # scoring the XGB model
        feature_cols = [
            'MACD_6_14',
            'MACD_12_26',
            'MACD_18_38',
            #'MACD_30_60',
            'VII_lead_3',
            'VII_lead_5',
            'VII_lead_10',
            'VII_lag_3',
            'VII_lag_5',
            'VII_lag_10',

            'VII_3_ratio',
            'VII_5_ratio',
            'VII_10_ratio',

            'price_diff',
            'ba_spread']

        df_lag['price_diff']=df_lag['lag_price_predicted']-df_lag['ask_price']
        df_lag['XGB_SCORE_LONG']=strategy_class.production_model_long.predict_proba(df_lag[feature_cols].apply(pd.to_numeric, errors='coerce'))[:, 1]

        df_lag['price_diff']=df_lag['lag_price_predicted']-df_lag['bid_price']
        df_lag['XGB_SCORE_SHORT']=strategy_class.production_model_short.predict_proba(df_lag[feature_cols].apply(pd.to_numeric, errors='coerce'))[:, 1]


        #df_lag.to_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dem2_jan_feb_enriched.csv')

        ###################################################################################################################
        ###

        price_dict = df_lag.to_dict('list')
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
