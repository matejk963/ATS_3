# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from itertools import product

from Strategies.Modular_strategy.calibration import ModularStrategyCalibration
from Strategies.Modular_strategy.backtest_class import BacktestModular
from Strategies.Modular_strategy.strategy_class_new import ModularStrategy as NewStrategy
from Utilities.Storage import get_curr_storage_path
from Strategies.Modular_strategy.features import *

def create_combinations():
    features = [
        'feature_order_t1',
        'feature_trd_gap',
        'feature_ba_spread',
        'make_profit_margin',
        'stop_loss',
        'stop_profit',
        'burnout_period',
        'makeagg_ratio'
    ]
    # Define parameter lists for each feature
    feature_order_t1_params = [{'active': True, 'suffix': ''}]
    # feature_model_params = [{'active': True}]

    feature_traded_abo_params = [{'active': True, 'params': {'thold': i}, 'suffix': ""} for i in
                                    [0.05, 0.06, 0.07, 0.08, 0.09, 0.1]]

    feature_ba_break_params = [{'active': True, 'params': {'thold_bas': i}, 'suffix': ""} for i in
                                [.11, 0.16, 0.41, 0.51]]
    # feature_scaled_sparsity = [{'active': True, 'params': {'thold': i}} for i in
    #                             [0.3, 0.5, 0.7, 0.8, 0.9]]
    # feature_interval_pdiff = [{'active': True, 'params': {'thold': i}} for i in
    #                             [0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1]]
    # feature_interval_int = [{'active': True, 'params': {'thold': i}} for i in
    #                             [0, 1, 2, 3, 4, 5]]
    # feature_close_level = [{'active': True, 'params': {'thold': i}} for i in
    #                         [-1.0, 0.3, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]]
    # feature_far_level = [{'active': True, 'params': {'thold': i}} for i in
    #                     [-1.0, 0.3, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]]
    # feature_p_movement = [{'active': True, 'params': {'thold': i}} for i in
    #                     [0.0, 0.3, 0.5, 0.7, 0.8, 0.9]]
    make_profit_params = [i for i in [.25, .3, 0.35, 0.4, 0.5, 0.6, 0.75]]
    stop_loss_params = [i for i in [.4]]
    stop_profit_params = [i for i in [.1, 0.15]]
    burnout_period_params = [i for i in [5, 10, 15, 20, 25, 30]]
    makeagg_ratio_params = [i for i in [0.6]]
    # Create all combinations
    all_params_combinations = product(feature_order_t1_params,
                                    feature_traded_abo_params,
                                    feature_ba_break_params,
                                    make_profit_params,
                                    stop_loss_params,
                                    stop_profit_params,
                                    burnout_period_params,
                                    makeagg_ratio_params)
    result = [
    dict(zip(features, params_combination))
        for params_combination in all_params_combinations
    ]
    # Iterate over combinations
    # for params_combination in all_params_combinations:
    #     param_dict = {
    #         'feature_order_t1': params_combination[0],
    #         'feature_model': params_combination[1],
    #         'make_profit_margin': params_combination[2],
    #         'stop_loss': params_combination[3],
    #         'stop_profit': params_combination[4],
    #         'burnout_period': params_combination[5],
    #         'makeagg_ratio': params_combination[6]
    #     }
    #     # Use param_dict in further processing
    #     result.append(param_dict)
    return result

def from_key_to_params(string, fixed_params):
    params = string.split('_')
    return {
        'feature_order_t1': {'active': True},
        'feature_model': {'active': True},
        'make_profit_margin': params[0],
        'stop_loss': params[1],
        'stop_profit': params[2],
        'burnout_period': params[3],
        'makeagg_ratio': params[4]
        **fixed_params
    }

def clean_ba_dupl(df_input):
    df = df_input[['b_price', 'a_price', 'trd_price']].copy()
    df['b_price_lag'] = df['b_price'].shift(1)
    df['a_price_lag'] = df['a_price'].shift(1)
    df['mask'] = (
        (df['b_price_lag'] != df['b_price']) |
        (df['a_price_lag'] != df['a_price']) |
        (~df['trd_price'].isna())
    )
    return df['mask']

if __name__ == '__main__':
    # Load data from pickle
    _STORAGE = get_curr_storage_path()
    df_data = pd.read_parquet(_STORAGE + "data_factory/backtest_obt_deq1_from2024July.parquet")
    df_data = df_data[~df_data['b_price'].isna()]
    df_data = df_data[clean_ba_dupl(df_data)]
    df_data = df_data.reset_index(names='timestamp')
    df_data['ba_spread'] = (df_data['a_price'] - df_data['b_price']).round(2)
    df_data.loc[df_data['trd_price'] > 0, 'trd_vol'] = 1
    day = datetime(2025, 1, 24).date()
    df_data = df_data[df_data['timestamp'].dt.date != day]

    df_data.reset_index(inplace=True, drop=True)
    df_data.reset_index(names='index', inplace=True)
    df = df_data

    # params
    fixed_params = {
        'br_fee': 0.04 / 2,
        't_end': time(17, 30),
        'hard_sl': 2.0,
        'closing_mode': 'Other',
        'close_trade_info': None
    }

    features_pool = {
        'feature_order_t1': FeatureOrderT1,
        'feature_ba_spread': FeatureBASpread
    }

    strategy_columns = df_data.columns.values


    combinations = create_combinations()
    # combinations = [combinations[255]] #TODO: 1st combination to check for errors
    data_columns = ['a_price_sparsity',
    'b_price_sparsity',
    'p_movement_0.3',
    'diff_a_price',
    'diff_b_price',
    'trd_gap',
    'action_abs_sum_1s',
    'action_sum_1s',
    'bid_t1',
    'ask_t1',
    'ba_spread']
    indices = df[df[data_columns].notnull().all(axis=1)].index.tolist()


    
    # Calibration
    cal_method = 'cumpnl'
    calibration_class = ModularStrategyCalibration(cal_method)

    
    # strategy columns are used for check whether 
    # there are data for every used feature 
    backtest_class = BacktestModular()

    calibration_class.change_strategy(NewStrategy, features_pool, strategy_columns)
    out_dict = calibration_class.calibrate_single_multip(
        df_data, backtest_class, combinations, None, fixed_params, indices, 70)

    result = pd.DataFrame(out_dict.items(), columns=['combination', 'pnl'])
    print(result.head())


