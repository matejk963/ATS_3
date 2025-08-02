# -*- coding: utf-8 -*-
"""
Created on Wed Dec 18 10:26:07 2024

@author: scasny
"""
from datetime import datetime, time
import pandas as pd
import numpy as np
from itertools import product
import pickle
from multiprocessing import Pool, cpu_count, shared_memory, Process, Manager
from tqdm.auto import tqdm

from Strategies.Modular_strategy.calibration import ModularStrategyCalibration
from Strategies.Modular_strategy.backtest_class import BacktestModular
from Strategies.Modular_strategy.strategy_class import ModularStrategy
from Strategies.Modular_strategy.strategy_class_new import ModularStrategy as NewStrategy
from Strategies.Modular_strategy.features import *
from Utilities.dfutils import date_filter, df_days_tag
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments

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
    feature_order_t1_params = [{'active': False, 'suffix': ''}]

    feature_traded_abo_params = [{'active': False, 'params': {'thold': i}, 'suffix': ""} for i in
                                    [0.1]]

    feature_ba_break_params = [{'active': False, 'params': {'thold_bas': i}, 'suffix': ""} for i in
                                [0.51]]
    make_profit_params = [i for i in [0.15, 0.17, 0.2, 0.25]]
    stop_loss_params = [i for i in [.4]]
    stop_profit_params = [i for i in [.1]]
    burnout_period_params = [i for i in [3, 5, 7, 10, 15]]
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

    return result
# params
fixed_params = {
    'br_fee': 0.04 / 2,
    't_end': time(17, 30),
    'hard_sl': 2.0,
    'closing_mode': 'Other',
    'close_trade_info': None
}

data_columns = ['a_price_sparsity',
    'b_price_sparsity',
    'trd_gap',
    'bid_t1',
    'ask_t1',
    'ba_spread']

features_pool = {
    'feature_order_t1': FeatureOrderT1,
    'feature_trd_gap': FeatureTradedAboveBO,
    'feature_ba_spread': FeatureBASpread
}

# params = {
#     'feature_sparsity': {'active': False, 'params': {'thold_dense': 0.26, 'thold_sparse': 0.09}, 'suffix': ""},
#     'feature_scaled_sparsity': {'active': False, 'params': {'thold': 0.46}, 'suffix': ""},
#     'feature_far_level': {'active': False, 'params': {'thold': 1.1}, 'suffix': ""},
#     'feature_p_movement': {'active': False, 'params': {'thold': 0.79}, 'suffix': ""},
#     'feature_ba_spread': {'active': False, 'params': {'thold_bas': 0.24, 'suffix': ""}},
#     'feature_order_t1': {'active': False, 'suffix': ""},
#     'make_profit_margin': 0.75,
#     'stop_loss': .4,
#     'stop_profit': .1,
#     'makeagg_ratio': 0.6,
#     'burnout_period': 30
# }

def split_list(items, n):
    k, m = divmod(len(items), n)
    return [items[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]

backtest_class = BacktestModular()

def pool_worker(args):
    strategy, np_arr, idxs = args
    # Attach to existing shared memory
    result = backtest_class.cache_return(strategy, np_arr, idxs)
    return result

def save_to_parquet(result, instrument, dir_path):
    # Convert nested dict to DataFrame
    rows = []
    for param_str, index_data in result.items():
        # Parse parameters from param_str
        params = param_str.split('_')
        for idx, values in index_data.items():
            rows.append({
                'make_profit_margin': float(params[0]),
                'stop_loss': float(params[1]),
                'stop_profit': float(params[2]),
                'burnout_period': int(params[3]),
                'index': int(idx),
                'short_i': values['short'][0],
                'short_r': values['short'][1],
                'long_i': values['long'][0],
                'long_r': values['long'][1]
            })
    
    df = pd.DataFrame(rows)
    filename = f"cache_r_{instrument}.parquet"
    df.to_parquet(_STORAGE + dir_path + filename, index=False)

if __name__ == '__main__':
    _STORAGE = get_curr_storage_path()
    # ------------------ dataset prep ---------------------------------
    args_config = {
        '--instrument': {'type': str, 'default': 'dey1'},
        '--directory_path': {'type': str, 'default': 'martin'}
    }

    # Load arguments
    _INSTRUMENT, _DIR_PATH = load_arguments(args_config)

    if _DIR_PATH == 'martin':
        df_data = pd.read_parquet(_STORAGE + f"data_factory/backtest_obt_{_INSTRUMENT}_from2024July.parquet")
    else:
        df_data = pd.read_parquet(_STORAGE + _DIR_PATH + f'backtest_obt_{_INSTRUMENT}.parquet')

    df_data = df_data[~df_data['b_price'].isna()]
    df_data = df_data[clean_ba_dupl(df_data)]
    df_data = df_data.reset_index(names='timestamp')
    df_data['ba_spread'] = (df_data['a_price'] - df_data['b_price']).round(2)
    df_data.loc[df_data['trd_price'] > 0, 'trd_vol'] = 1
    day = datetime(2025, 1, 24).date()
    df_data = df_data[df_data['timestamp'].dt.date != day]
    df_data = df_days_tag(df_data)
    
    
    df_data.reset_index(inplace=True, drop=True)
    df_data.reset_index(names='index', inplace=True)
    strategy_columns = df_data.columns.values
    
    indices = df_data[df_data[data_columns].notnull().all(axis=1)].index.tolist()
    
    # --------------------- end -----------------------------------------
    
    
    
    # ------------------ multi processing part -----------------------------
    combinations = create_combinations()
    result = {}
    for i, params in enumerate(combinations):
        print("   processing combination",i, "/", len(combinations))
        strategy = NewStrategy(features_pool, strategy_columns,
                                {**params, **fixed_params},
                                 lead_closing=False, max_position=1)
        grouped = df_data.groupby('day')
        matrices = [group.to_numpy() for _, group in grouped]
        split_idxs = [group.index.values[group.index.isin(indices)] for _, group in grouped]
        
        num_processes = 20
        
        with Pool(processes=num_processes) as pool:
            args_list = [(strategy,
                          np_arr, idxs) for np_arr, idxs in zip(matrices, split_idxs)]
            result_dict = list(tqdm(
                pool.imap(pool_worker, args_list),
                total=len(matrices),
                desc="Processing",
                unit='days'
            ))
                
        returns = {}
        for d in result_dict:
           returns.update(d)
        
        param_str = "_".join([str(v) for k, v in params.items() if k in ['make_profit_margin', 'stop_loss', 'stop_profit', 'burnout_period']])
        result[param_str] = returns
           

    date_min = df_data['timestamp'].dt.date.min()
    date_max = df_data['timestamp'].dt.date.max()
    filename = _STORAGE + _DIR_PATH + f"cache_r_{_INSTRUMENT}"
    # with open(_STORAGE + f"martin/{filename}.pkl", "wb") as f:
    #     pickle.dump(result, f)
    save_to_parquet(result, _INSTRUMENT, _DIR_PATH)