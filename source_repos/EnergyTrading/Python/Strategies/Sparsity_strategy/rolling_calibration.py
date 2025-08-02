# -*- coding: utf-8 -*-
"""
Created on Thu Dec 19 10:15:57 2024

@author: scasny
"""

# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
"""
from time import sleep
from datetime import datetime, time
import pandas as pd
import numpy as np
from itertools import product
import hdbscan
from scipy.spatial.distance import cdist
import pickle
import torch
from tqdm import tqdm
import heapq
import warnings
warnings.filterwarnings("ignore")

from Strategies.Modular_strategy.calibration import ModularStrategyCalibration
from Strategies.Modular_strategy.backtest_class import BacktestModular
from Strategies.Modular_strategy.strategy_class import ModularStrategy
from Strategies.Modular_strategy.strategy_class_new import ModularStrategy as NewStrategy
from Strategies.Modular_strategy.features import *
import Strategies.Modular_strategy.features_tensor as TensorFeature
from Strategies.Modular_strategy.features_tensor import TensorDataWrapper
from Utilities.func_utils import execution_time
from Utilities.torch_utils import device_agnostic, TensorTracker, format_bytes, print_line, print_section
from Utilities.DataValidator import assert_pair
from Utilities.Storage import get_curr_storage_path
from Utilities.func_utils import load_arguments, execution_time


def custom_loss(n, curr_pnl, tp, def_ret):
    optimal_pnl = n * tp * 0.5 + n * def_ret
    baseline_pnl = n * def_ret
    return (optimal_pnl - curr_pnl) / (optimal_pnl - baseline_pnl)

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

def get_batch_indices(combs_shape, start_idx, batch_size, device):
    """Generate multi-dimensional indices for a batch of combinations"""
    # Generate linear indices
    end_idx = min(start_idx + batch_size, torch.prod(combs_shape).item())
    linear = torch.arange(start_idx, end_idx, device=device)
    
    # Calculate strides for each dimension
    strides = torch.cumprod(combs_shape.flip(0), 0).flip(0)
    strides = torch.cat((strides[1:], torch.tensor([1], device=device)))
    
    # Convert to multi-dimensional indices
    return (linear.unsqueeze(1) // strides) % combs_shape

def compute_combined_mask(MDX, batch_indices):
    """Compute combined boolean mask for a batch of indices"""
    # Initialize mask as boolean tensor
    mask = torch.ones(MDX[0].shape[0], batch_indices.shape[0], 
                    dtype=torch.bool, device=batch_indices.device)
    
    for dim, mdx_tensor in enumerate(MDX):
        dim_cols = batch_indices[:, dim]
        # Ensure gathered columns are boolean
        current_mask = mdx_tensor[:, dim_cols].bool()  # Explicit cast
        mask &= current_mask
        
    return mask

def load_optimized_cache(filename, device):
    # Read only necessary columns
    _STORAGE = get_curr_storage_path()
    df = pd.read_parquet(_STORAGE + f"martin/{filename}", 
                         columns=['make_profit_margin', 'stop_loss', 'stop_profit', 'burnout_period', 'index', 'short_r', 'long_r'],
                         engine='pyarrow')
    
    # Create combination strings efficiently
    df['comb'] = (df['make_profit_margin'].astype(str) + '_' + 
                  df['stop_loss'].astype(str) + '_' + 
                  df['stop_profit'].astype(str) + '_' + 
                  df['burnout_period'].astype(str))
    
    # Get unique combinations and indices
    combination_keys = df['comb'].unique()
    unique_indices = df['index'].unique()
    
    # Create mappings
    comb_to_col = {comb: i for i, comb in enumerate(combination_keys)}
    index_to_row = {idx: i for i, idx in enumerate(unique_indices)}
    
    # Initialize matrices
    n_rows, n_comb = len(unique_indices), len(combination_keys)
    short_matrix = np.zeros((n_rows, n_comb), dtype=np.float16)
    long_matrix = np.zeros((n_rows, n_comb), dtype=np.float16)
    
    # Vectorized population of matrices
    row_indices = np.array([index_to_row[idx] for idx in df['index']])
    col_indices = np.array([comb_to_col[comb] for comb in df['comb']])
    
    short_matrix[row_indices, col_indices] = df['short_r'].values
    long_matrix[row_indices, col_indices] = df['long_r'].values
    
    return {
        'short': torch.tensor(short_matrix, dtype=torch.float16, device=device),
        'long': torch.tensor(long_matrix, dtype=torch.float16, device=device),
        'combinations': combination_keys.tolist()
    }

def restructure_cache_data(original_data):
    # Get all combination keys
    combination_keys = list(original_data.keys())

    # Get all item keys from the first combination
    item_keys = list(original_data[combination_keys[0]].keys())

    # Prepare new data structure
    n_rows = len(item_keys)
    n_combinations = len(combination_keys)

    # Initialize numpy arrays for short and long returns
    short_matrix = np.zeros((n_rows, n_combinations))
    long_matrix = np.zeros((n_rows, n_combinations))

    # Fill the matrices
    for col_idx, comb_key in enumerate(combination_keys):
        for row_idx, item_key in enumerate(item_keys):
            short_matrix[row_idx, col_idx] = original_data[comb_key][item_key]['short'][1]
            long_matrix[row_idx, col_idx] = original_data[comb_key][item_key]['long'][1]

    # Create new structure
    new_structure = {
        'short': short_matrix,
        'long': long_matrix,
        'combinations': combination_keys
    }

    return new_structure

def calculate_scores(mask, cache_tensors, cache_dims=(8, 8)):
    """Calculate normalized scores for combinations with configurable cache dims"""
    # Expand mask dimensions to match cache_tensors
    """Added tensor size debugging"""
    for _ in range(len(cache_dims)):
        mask = mask.unsqueeze(-1)
    
    # Convert mask to same dtype as cache_tensors for multiplication
    mask = mask.to(cache_tensors.dtype)
    
    # Vectorized calculation using broadcasting
    gathered = cache_tensors.unsqueeze(1) * mask  # (num_rows, batch_size, *cache_dims)
    
    # Sum over rows and cache dimensions
    sum_dims = (0,) + tuple(range(2, 2 + len(cache_dims)))  # Sum over num_rows and cache dims
    summed = gathered.sum(dim=sum_dims)
    
    # Calculate normalization factor
    divisor = torch.prod(torch.tensor(cache_dims, device=cache_tensors.device))
    
    return summed / divisor

def compute_mask_single(tdw: TensorDataWrapper, features, combination, cache_short, cache_long):
    MDX_short, MDX_long = [], []
    for k, v in features.items():
        cls_obj = v['class']
        unpack_list = len(cls_obj.thold_columns) > 1
        
        bool_short = cls_obj.condition_short(tdw)
        bool_long = cls_obj.condition_long(tdw)
        MDX_short.extend(bool_short if unpack_list else [bool_short])
        MDX_long.extend(bool_long if unpack_list else [bool_long])
        
    
def calculate_scores_2dim(mask_short, mask_long, cache_short, cache_long, indices):
    """Calculate normalized scores for combinations with configurable cache dims"""
    """Calculate normalized scores for combinations with row indices"""
    # Select only rows specified by indices
    cache_short_selected = cache_short[indices]
    cache_long_selected = cache_long[indices]
    
    # Convert mask to same dtype as cache_tensors
    mask_short = mask_short.to(cache_short_selected.dtype)
    mask_long = mask_long.to(cache_long_selected.dtype)
    
    # Align dimensions for broadcasting
    mask_short = mask_short.unsqueeze(-1)
    mask_long = mask_long.unsqueeze(-1)
    
    cache_short_selected = cache_short_selected.unsqueeze(1)
    cache_long_selected = cache_long_selected.unsqueeze(1)

    # Vectorized calculation with broadcasting
    gathered_short = mask_short * cache_short_selected
    gathered_long = mask_long * cache_long_selected
    
    # Sum over batch dimension (dim=0)
    summed_short = gathered_short.sum(dim=0)
    summed_long = gathered_long.sum(dim=0)
    
    return summed_short + summed_long
    
def calculate_scores_all(mask_short, mask_long, cache_short, cache_long):
    """Calculate normalized scores for combinations with configurable cache dims"""
    # Convert mask to same dtype as cache_tensors for multiplication
    mask_short = mask_short.to(cache_short.dtype)
    mask_long = mask_long.to(cache_long.dtype)
    
    # Align dimensions for broadcasting
    # mask_short = mask_short.unsqueeze(-1).unsqueeze(-1)  # Shape [20000, 2048, 1, 1]
    # mask_long = mask_long.unsqueeze(-1).unsqueeze(-1)  # Shape [20000, 2048, 1, 1]
    cache_short = cache_short.unsqueeze(1)  # Shape [20000, 1, 1, 1]
    cache_long = cache_long.unsqueeze(1)  # Shape [20000, 1, 1, 1]

    # Vectorized calculation with broadcasting
    gathered_short = mask_short * cache_short # Result shape [20000, 2048, 1, 1]
    gathered_long = mask_long * cache_long   # Result shape [20000, 2048, 1, 1]
    
    # Sum over batch (dim=0) and cache dimensions (dims=2,3)
    summed_short = gathered_short.sum(dim=(0))  # Result shape [2048]
    summed_long = gathered_long.sum(dim=(0))  # Result shape [2048] batch_size = 2048
    
    return summed_short + summed_long

def update_topk_heap(heap, scores, indices, counter, top_k):
    """Update heap with new batch of scores and indices"""
    for score, idx in zip(scores, indices):
        if score > heap[0][0]:
            # Push new element and pop smallest
            heapq.heappushpop(heap, (score.item(), counter, idx))
            counter += 1
    return counter

def process_batches_all(MDX_short, MDX_long, cache_short, cache_long, cache_indices, combs_shape, device, batch_size, gpu_temp_limit=90):
    # Initialize progress bar
    total_combs = torch.prod(combs_shape).item()
    pbar = tqdm(total=total_combs, desc="Torch batch processing", unit="combs")
    dim_limits = torch.tensor([t.shape[1] for t in MDX_short], device=device)
    result_combinations = torch.zeros((total_combs, combs_shape.shape[0]), device=device, dtype=torch.int8)
    result_scores = torch.zeros((total_combs, 1), device=device, dtype=torch.float16)
    # Add tensor to store the best combination indices
    result_best_comb_idx = torch.zeros((total_combs, 1), device=device, dtype=torch.int16)
    
    print('Estimated memory usage:', (total_combs * combs_shape.shape[0] + total_combs * 2) / 1024**2, 'MB')
    try:
        for batch_start in range(0, total_combs, batch_size):
            try:
                temperature = torch.cuda.temperature()
                if temperature > gpu_temp_limit:
                    while torch.cuda.temperature() > 55:
                        sleep(1)
                        print("   ...cooling gpu in process [", torch.cuda.temperature(), "]")
                        temperature = torch.cuda.temperature()
            except:
                temperature = 0 
                pass
                
            batch_indices = get_batch_indices(combs_shape, batch_start, batch_size, device)
            safe_indices = torch.minimum(batch_indices, dim_limits - 1)
            mask_short = compute_combined_mask(MDX_short, safe_indices)
            mask_long = compute_combined_mask(MDX_long, safe_indices)

            batch_scores = calculate_scores_2dim(mask_short, mask_long, cache_short, cache_long, cache_indices)
            
            # Find the best score and its index for each batch item
            best_scores, best_comb_indices = batch_scores.max(dim=1)
            
            # Get actual batch size (important for the last batch)
            actual_batch_size = min(batch_size, total_combs-batch_start)
            
            # Store results
            result_combinations[batch_start:batch_start+actual_batch_size, :] = batch_indices[:actual_batch_size]
            result_scores[batch_start:batch_start+actual_batch_size, 0] = best_scores[:actual_batch_size]
            result_best_comb_idx[batch_start:batch_start+actual_batch_size, 0] = best_comb_indices[:actual_batch_size]
            
            pbar.update(actual_batch_size)
            pbar.set_postfix({
                'mem': format_bytes(torch.cuda.memory_allocated()) if torch.cuda.is_available() else "",
                'gpu_temp': temperature
            })

        pbar.close()

        # Convert to pandas DataFrame
        result_df = pd.DataFrame({
            'comb': result_combinations.cpu().tolist(),
            'score': result_scores.cpu().squeeze(1).tolist(),
            'best_comb_idx': result_best_comb_idx.cpu().squeeze(1).tolist()
        })
        return result_df

    except RuntimeError as e:
        if 'out of memory' in str(e).lower():
            new_size = max(batch_size//2, 1)
            print(f"OOM Error! Trying smaller batch size: {new_size}")
            return None
        raise    

def process_batches_with_topk(MDX, cache_tensors, combs_shape, 
                            device, top_k=10000, batch_size=2**13, verbose=False):
    """
    Added features:
    - tqdm progress bar
    - Dynamic memory updates
    - Batch size validation
    """

    # Initialize progress bar
    total_combs = torch.prod(combs_shape).item()
    pbar = tqdm(total=total_combs, desc="Torch batch processing", unit="combs")
    
    # Existing code...
    heap = []
    counter = 0
    for _ in range(top_k):
        heapq.heappush(heap, (float('-inf'), counter, torch.tensor([], device='cpu')))
        counter += 1

    dim_limits = torch.tensor([t.shape[1] for t in MDX], device=device)
    
    # Add memory check before processing
    try:
        for batch_start in range(0, total_combs, batch_size):


            # Existing processing code...
            batch_indices = get_batch_indices(combs_shape, batch_start, batch_size, device)
            safe_indices = torch.minimum(batch_indices, dim_limits - 1)
            mask = compute_combined_mask(MDX, safe_indices)
            batch_scores = calculate_scores(mask, cache_tensors)

            if verbose:
                TRACKER = TensorTracker()
                TRACKER._track_tensor(batch_indices, name='batch_indices')
                TRACKER._track_tensor(safe_indices, name='safe_indices')
                TRACKER._track_tensor(mask, name='mask')
                TRACKER._track_tensor(batch_scores, name='batch_scores')


            counter = update_topk_heap(heap, batch_scores, safe_indices, counter, top_k)

            # Update progress bar
            pbar.update(batch_size)
            pbar.set_postfix({
                'min_score': f"{heap[0][0]:.2f}",
                'mem': format_bytes(torch.cuda.memory_allocated()) if torch.cuda.is_available() else ""
            })
            torch.cuda.empty_cache()

            if verbose: print(TRACKER.get_memory_summary())
                
    except RuntimeError as e:
        if 'out of memory' in str(e).lower():
            new_size = max(batch_size//2, 1)
            print(f"OOM Error! Trying smaller batch size: {new_size}")
            return None
        raise
    
    pbar.close()
    
    return sorted([(score, idxs) for score, _, idxs in heap if score > float('-inf')], 
                key=lambda x: -x[0])


def df_days_tag(df):
    unique_dates = df['timestamp'].dt.date.unique()
    
    # Create a dictionary to map unique dates to tags
    date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
    
    # Add a new column for the tags
    df['day'] = df['timestamp'].dt.date.map(date_to_tag)
    
    return df.copy()

def from_key_to_params(params, fixed_params, features_pool):
    if isinstance(params, str):
        params = params.split('_')

    ptr = 0
    result = {}
    
    for feature_name, feature_class in features_pool.items():        
        # Now call get_t() on the instance
        threshold_count = len(feature_class.get_t())
        suffix = feature_name.split("_")[-1] if 'sfx' in feature_name else ""
        feature_config = {'active': True}
        
        if threshold_count > 0:
            feature_params = params[ptr:ptr+threshold_count]
            ptr += threshold_count
            feature_config['params'] = {
                f'thold_{i+1}': param 
                for i, param in enumerate(feature_params)
            }
        feature_config['suffix'] = suffix

        result[feature_name] = feature_config
    
    return {**result, **fixed_params}

def indices_to_parameters(indices, param_vectors):
    import math
    parameters = []
    for idx, vector in zip(indices, param_vectors):
        vector = vector.cpu().numpy().tolist()
        lower = math.floor(idx)
        upper = math.ceil(idx)
        parameters.append(round(float(vector[lower] + (vector[upper] - vector[lower])*(idx%1)), 2))
    return parameters


if __name__ == '__main__':
    # args_config = {
    #     '--batch_size': {'type': int, 'default': 2**8, 'help': 'Batch size for training'},
    #     '--cache_r_path': {'type': str, 'default': 'data_factory/backtest_obt_dem1_from2024July.parquet', 'help': 'Path to cache file'},
    #     '--top_k': {'type': int, 'default': 500, 'help': 'Top K elements to consider'},
    #     '--mode': {'type': str, 'default': 'gpu', 'help': 'Torch device mode (cpu or gpu)'},
    #     '--cpu_cores': {'type': int, 'default': 4, 'help': 'Percentage of CPU cores to use'},
    # }
    args_config = {
        '--instrument': {'type': str, 'default': 'deq2'},
        '--top_k': {'type': int, 'default': 500},
        '--fees': {'type': float, 'default': 0.04},
        '--train_days': {'type': int, 'default': 20},
        '--cluster_size': {'type': int, 'default': 5},
        '--directory_path': {'type': str, 'default': 'default/'}
    }

    # Load arguments
    print_section("Loading arguments")
    _INSTRUMENT, _TOP_K, _FEES, _TRAIN_DAYS, _CLUSTER_SIZE, _DIR_PATH = load_arguments(args_config)
    device = device_agnostic() # Set device mode

    print(_INSTRUMENT, _TOP_K, _FEES, _TRAIN_DAYS, _CLUSTER_SIZE, _DIR_PATH, sep='\n')
    STORAGE_PATH = get_curr_storage_path()
    BATCH_SIZE = 128
    data_columns = ['a_price_sparsity',
    'b_price_sparsity',
    'p_movement_0.3',
    'trd_gap',
    'action_abs_sum_1s',
    'action_sum_1s',
    'bid_t1',
    'ask_t1',
    'ba_spread']

    # Load data from pickle
    print_line()
    file_path = STORAGE_PATH + f"data_factory/backtest_obt_{_INSTRUMENT}_from2024July.parquet"
    print(f"Loading file: {file_path}")
    
    df_raw = pd.read_parquet(file_path)
    print_line()
    
    print_section('Data preprocessing')
    df_raw = df_raw[~df_raw['b_price'].isna()]
    df_data = df_raw[clean_ba_dupl(df_raw)]
    del df_raw
    df_data = df_data.reset_index(names='timestamp')
    df_data['ba_spread'] = (df_data['a_price'] - df_data['b_price']).round(2)
    df_data.loc[df_data['trd_price'] > 0, 'trd_vol'] = 1
    day = datetime(2025, 1, 24).date()
    df_data = df_data[df_data['timestamp'].dt.date != day]
    df_data = df_days_tag(df_data)
    df_data.reset_index(inplace=True, drop=True)
    df_data.reset_index(names='index', inplace=True)
    df_obt = df_data.copy()
    df_data = df_data[df_data[data_columns].notnull().all(axis=1)]
    # df_data = df_data[pd.notna(df_data['trd_price'])]
    
    print_line()
    
    backtest_class = BacktestModular()
    

    print_section('Loading cached returns...')
    # try:
    #     with open(STORAGE_PATH + f"martin/cache_r_{_INSTRUMENT}_2024-07-01_2025-03-05.pkl", "rb") as f:
    #         cached_r = pickle.load(f)
    # except EOFError:
    #     print("The file is empty or corrupted")
    # except FileNotFoundError:
    #     print("The file does not exist")
    #TODO: cached_r 
    FEES = _FEES
    cache_data = load_optimized_cache("test_cache_r_deq2_2024-07-01_2025-03-05.parquet", device)
    cache_short = cache_data['short'] - FEES
    cache_long = cache_data['long'] - FEES
    cache_combinations = cache_data['combinations']
    print_line()
    # assert_pair(len(list(cached_r)), df_data.shape[0], '(cached_returns, df_data) shape')
    
    # params


    # featurs for 2nd step precise calibration
    features_pool = {
        'feature_sparsity': FeatureSparsity,
        # 'feature_far_level': FeatureFarLevel,
        # 'feature_bo_diff': FeatureBODiff,
        'feature_trd_gap': FeatureTradedAboveBO,
        # 'feature_action_abs_sum_sfx_1s': FeatureActionAbsSum,
        # 'feature_action_sum_sfx_1s': FeatureActionSum,
        # 'feature_p_movement': FeaturePMovement,
        'feature_ba_spread': FeatureBASpread,
        'feature_order_t1': FeatureOrderT1
    }

    # features for torch processing
    features = {
        'FeatureSparsity': {
            'class': TensorFeature.FeatureSparsity,
            'th_feat_sp_dense': [0.11, 0.16, 0.21, 0.26, 1.0],
            'th_feat_sp_sparse': [0.0, 0.04, 0.07, 0.09, 0.12, 0.14, 0.19, 0.24, 0.29, 0.39]
        },
        # 'FeatureFarLevel': {
        #     'class': TensorFeature.FeatureFarLevel,
        #     'th_feat_far_level': [1.1, 0.7, 0.5, 0.25, 0.1]
        # },
        'FeatureBODiff': {
            'class': TensorFeature.FeatureBODiff,
            'th_feat_bo_diff': [-0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.1]},
        'FeatureTrdGap': {
            'class': TensorFeature.FeatureTrdGap,
            'th_feat_trd_gap': [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12]},
        'FeatureActionAbsSum': {
            'class': TensorFeature.FeatureActionAbsSum,
            'th_feat_action_abs_sum_1s': [0.0, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0]},
        'FeatureActionSum': {
            'class': TensorFeature.FeatureActionSum,
            'th_feat_action_sum_1s': [-1.1, -0.5, 0.0, 0.3, 0.5, 0.7, 0.9]},
        'FeaturePMovement': {
            'class': TensorFeature.FeaturePMovement,
            'th_feat_p_movement03': [-1.1, -0.5, 0.0, 0.3, 0.5, 0.7, 0.9]},
        'FeatureBASpread': {
            'class': TensorFeature.FeatureBASpread,
            'th_feat_ba_spread': [0.11, 0.16, 0.21, 0.41, 1.0]
        },
        'FeatureOrderT1': {
            'class': TensorFeature.FeatureOrderT1,
            'th_feat_order_t1': [1.0]}
    }
    
    # DEBUG comment if not needed
    features = {
        'FeatureSparsity': {
            'class': TensorFeature.FeatureSparsity,
            'th_feat_sp_dense': [0.11, 0.16, 0.21, 0.26, 0.4, 0.5, 0.6, 1.1],
            'th_feat_sp_sparse': [-0.1, 0.0, 0.04, 0.07, 0.09, 0.12, 0.14, 0.19, 0.24, 0.29, 0.39]
        },

        # 'FeatureBODiff': {
        #     'class': TensorFeature.FeatureBODiff,
        #     'th_feat_bo_diff': [-1.0, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.1]},
        'FeatureTrdGap': {
            'class': TensorFeature.FeatureTrdGap,
            'th_feat_trd_gap': [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 0.11]},
        # 'FeatureActionAbsSum': {
        #     'class': TensorFeature.FeatureActionAbsSum,
        #     'th_feat_action_abs_sum_1s': [-0.1, 1.0]},
        # 'FeatureActionSum': {
        #     'class': TensorFeature.FeatureActionSum,
        #     'th_feat_action_sum_1s': [-1.1, -0.5, 0.0]},

        # 'FeaturePMovement': {
        #     'class': TensorFeature.FeaturePMovement,
        #     'th_feat_p_movement03': [-1.1, -0.5, 0.0, 0.5, 0.75, 0.9]},
        'FeatureBASpread': {
            'class': TensorFeature.FeatureBASpread,
            'th_feat_ba_spread': [0.11, 0.16, 0.21, 0.26, 0.31, 0.41, 0.51, 1.0]
        },
        'FeatureOrderT1': {
            'class': TensorFeature.FeatureOrderT1,
            'th_feat_order_t1': [1.0]}
    }

    feature_list = []
    for key, feature in features.items():
        feature_list.extend([{k: th_list} for k, th_list in feature.items() if 'class' not in k])

    features_order = []
    thold_list = []

    for item in feature_list:
        feat, vector = list(item.items())[0]
        features_order.append(feat)
        thold_list.append(vector)
        
    thold_tensors = [torch.tensor(sublist, device=device, dtype=torch.float16) for sublist in thold_list]
    x_shapes = torch.tensor([x.shape[0] for x in thold_tensors], device=device)

    strategy_columns = df_data.columns.values

    train_days = _TRAIN_DAYS
    test_days = 5
    step = 5
    max_day = df_data.day.max()
    data_set_dict = {range_tuple: {} for range_tuple in [
        (train_start, train_start+(train_days-1), train_start+(train_days+test_days-1)) for train_start in range(
            0, max_day-(train_days+test_days), step)]}
    
    # Create an array mapping index to row in the matrices
    all_indices = df_data['index'].values
    index_to_row = {idx: i for i, idx in enumerate(all_indices)}
    
    for date_tuple in data_set_dict.keys():
        train_range = range(date_tuple[0], date_tuple[1]+1)
        test_range = range(date_tuple[1]+1, date_tuple[2]+1)
        
        # Get dataframes as before
        data_set_dict[date_tuple]['train'] = df_data[df_data['day'].isin(train_range)]
        data_set_dict[date_tuple]['test'] = df_data[df_data['day'].isin(test_range)]
        
        # Get the row indices for matrices instead of filtering dictionary
        train_indices = data_set_dict[date_tuple]['train']['index'].values
        test_indices = data_set_dict[date_tuple]['test']['index'].values
        
        # Store row indices for the matrices
        data_set_dict[date_tuple]['train_indices'] = [index_to_row[idx] for idx in train_indices if idx in index_to_row]
        data_set_dict[date_tuple]['test_indices'] = [index_to_row[idx] for idx in test_indices if idx in index_to_row]
            
    
    test_results = {
        'start_train': [],
        'end_train': [],
        'best_indices': [],
        'train_score': [],
        'start_test': [],
        'end_test': [],
        'parameters': [],
        'closing_params': [],
        'pnl': [],
        'def_ret': [],
        'mean': [],
        'count': [],
        'acc': [],
        'custom_loss': []
        
    }
    
    iteration = 0
    for date in data_set_dict:
        print('iteration', iteration, 'out of', len(list(data_set_dict)))
        df_train = data_set_dict[date]['train']
        df_test = data_set_dict[date]['test']
        indices = df_train[df_train[data_columns].notnull().all(axis=1)].index.tolist()

        # ----------------- TORCH calib -------------------------------------
        D = torch.stack([torch.tensor(df_train[col].values) for col in data_columns], dim=1).to(device, dtype=torch.float16)
        tdw = TensorDataWrapper(D, 
                                data_columns, 
                                features_order, 
                                thold_tensors)
        # MDX 
        # shape (n_rows, x_length)
        # dtype:= bool
        print_section("features bool comparison -> MDXs")
        MDX_short, MDX_long = [], []
        for k, v in features.items():
            cls_obj = v['class']
            unpack_list = len(cls_obj.thold_columns) > 1
            
            bool_short = cls_obj.condition_short(tdw)
            bool_long = cls_obj.condition_long(tdw)
            MDX_short.extend(bool_short if unpack_list else [bool_short])
            MDX_long.extend(bool_long if unpack_list else [bool_long])
        
        df_score = process_batches_all(MDX_short, MDX_long, cache_short, cache_long, data_set_dict[date]['train_indices'], x_shapes, device, BATCH_SIZE)
        print_section("Sorting combinations")
        df_top_combs = df_score.sort_values(ascending=False, by='score')[:_TOP_K]
        # ----------------- TORCH end ------------------------        
        #  |
        # \/
        # -------------- Combinations clustering ------------------------------------
        df = df_top_combs.copy()
        CLUSTER_SIZE = _CLUSTER_SIZE

        # # Create a new DataFrame with individual items as columns
        param_df = pd.DataFrame(df["comb"].tolist(), columns=[f"x_{i}" for i in range(len(df["comb"].iloc[0]))], index=df.index)
        param_df['closing'] = df['best_comb_idx']
        # print_section("HDBSCAN clustering")
        param_df.columns = [f"x{i+1}" for i in range(param_df.shape[1])]

        param_df['objective'] = df_top_combs['score']
        # high_obj_threshold = param_df['objective'].quantile(0.5)
        # # Filter high objective points (e.g., top 10%);
        high_obj_points = param_df

        # Apply HDBSCAN clustering
        clusterer = hdbscan.HDBSCAN(min_cluster_size=CLUSTER_SIZE)
        print(f'   -> fit on points with shape {high_obj_points.shape}')
        cluster_labels = clusterer.fit_predict(high_obj_points)
        # Add labels to the DataFrame
        high_obj_points.loc[:, 'cluster'] = cluster_labels
        print(high_obj_points.groupby('cluster').agg('mean'))
        # Assuming objective_summary is ;already calculated
        objective_summary = high_obj_points.groupby('cluster')['objective'].agg(['mean', 'std', 'count'])
        print(objective_summary)
        # Calculate a score for each cluster (higher is better)
        objective_summary['score'] = objective_summary['mean'] / (objective_summary['std'] + 1)  # Adding 1 to avoid division by zero

        # Sort clusters by score in descending order
        best_clusters = objective_summary.sort_values('score', ascending=False)

        if len(best_clusters) > 1:
            # Select the best cluster (excluding -1)
            best_cluster = best_clusters[best_clusters.index != -1].iloc[0]
        else:
            best_cluster = best_clusters.iloc[0]
        # Get the parameters for the best cluster
        best_cluster_points = high_obj_points[high_obj_points['cluster'] == best_cluster.name]
        best_indices = best_cluster_points.mean().values[:-2]
        clusters = high_obj_points.groupby('cluster').agg('mean')
        clusters_dict = {}
        for i in range(len(clusters.index.values)):
            clusters_dict[i] = clusters.iloc[i].values[:-1]
        print_section('Run best clusters parameters in simulation')
        
        
        cluster_sharps = []
        for i,v in clusters_dict.items():
            p = indices_to_parameters(v[:-1], thold_tensors)
            closing_params = cache_combinations[round(v[-1])].split('_')
            fixed_template = {
                    'make_profit_margin': float(closing_params[0]),
                    'stop_loss': float(closing_params[1]),
                    'stop_profit': float(closing_params[2]),
                    'burnout_period': float(closing_params[3]),
                    'makeagg_ratio': 0.6,
                    'br_fee': 0.08 / 2,
                    't_end': time(17, 30),
                    'hard_sl': 1.0,
                    'closing_mode': 'Other',
                    'close_trade_info': None
            }
            print("   Running parameters", i, p)
            
            params = from_key_to_params(p, fixed_template, features_pool)
            strategy = NewStrategy(features_pool, strategy_columns,
                            params, 
                            lead_closing=False, max_position=1)
            
            indices = df_train[df_train[data_columns].notnull().all(axis=1)].index.tolist()
            backtest_class.simulate_strategy(strategy, df_obt, indices, cached_returns=None)
            xx = backtest_class.calc_returns_new(strategy)
            if not xx.empty:
                fees = (abs(xx.iloc[0]['position']) + abs(xx['action']).sum())*fixed_template['br_fee']
                current_pnl = xx['returns'].sum()-fees
                overall_mean = xx['returns'].mean()
                positive_mean = xx[xx['returns'] > 0]['returns'].mean()
                negative_mean = xx[xx['returns'] < 0]['returns'].mean()
                count = xx.shape[0]
                sharp = (xx['returns'].sum()-fees)/xx['returns'].dropna().std()
                
                # Print accuracy
                accuracy = sum(xx['returns'] > 0) / (len(xx)/2)
            else:
                current_pnl = 0.0
                overall_mean = 0.0
                accuracy = 0.0
                count = 0
                sharp = -999.9
                
            obj_f = sharp/max(count, 20)
            cluster_sharps.append(obj_f)
            print('objective func', obj_f)
            print('current_pnl', current_pnl)
            print('sharp ratio', sharp)
            print('overral_mean', overall_mean)
            print('count', count)
        p = clusters_dict[cluster_sharps.index(max(cluster_sharps))]
        best_parameters = indices_to_parameters(p[:-1], thold_tensors)
        best_closing = cache_combinations[round(p[-1])].split('_')
        # ------------------------------------------------------------------------
        #  |
        # \/
        # ------------ Run best combination on TEST DATA --------------------------
        print_section("Run the best comb on TEST data")
        fixed_template = {
                'make_profit_margin': float(best_closing[0]),
                'stop_loss': float(best_closing[1]),
                'stop_profit': float(best_closing[2]),
                'burnout_period': float(best_closing[3]),
                'makeagg_ratio': 0.6,
                'br_fee': 0.04 / 2,
                't_end': time(17, 30),
                'hard_sl': 1.0,
                'closing_mode': 'Other',
                'close_trade_info': None
        }
        
        params = from_key_to_params(best_parameters, fixed_template, features_pool)
        strategy = NewStrategy(features_pool, strategy_columns,
                        params, 
                        lead_closing=False, max_position=1)
        
        indices = df_test[df_test[data_columns].notnull().all(axis=1)].index.tolist()
        backtest_class.simulate_strategy(strategy, df_obt, indices, cached_returns=None)
        xx = backtest_class.calc_returns_new(strategy)
        if not xx.empty:
            fees = (abs(xx.iloc[0]['position']) + abs(xx['action']).sum())*fixed_template['br_fee']
            current_pnl = xx['returns'].sum()-fees
            overall_mean = xx['returns'].mean()
            positive_mean = xx[xx['returns'] > 0]['returns'].mean()
            negative_mean = xx[xx['returns'] < 0]['returns'].mean()
            count = xx.shape[0]
            
            # Print accuracy
            accuracy = sum(xx['returns'] > 0) / (len(xx)/2)
        else:
            current_pnl = 0.0
            overall_mean = 0.0
            accuracy = 0.0
            count = 0
        print('Test pnl: ', current_pnl, 'count: ', count)
        test_results['start_train'].append(df_train['timestamp'].dt.date.min())
        test_results['end_train'].append(df_train['timestamp'].dt.date.max())
        test_results['train_score'].append(best_cluster)
        test_results['best_indices'].append(best_indices)
        test_results['start_test'].append(df_test['timestamp'].dt.date.min())
        test_results['end_test'].append(df_test['timestamp'].dt.date.max())
        test_results['parameters'].append("_".join(map(lambda x: str(round(x, 2)), best_parameters)))
        test_results['closing_params'].append(best_closing)
        test_results['pnl'].append(current_pnl)
        test_results['mean'].append(overall_mean)
        test_results['count'].append(count)
        test_results['acc'].append(accuracy)

        # test_cache_short = [x['short'][1] for x in data_set_dict[date]['test_returns'].values()]
        # test_cache_long = [x['long'][1] for x in data_set_dict[date]['test_returns'].values()]
        # test_results['def_ret'].append(0.5 * (np.mean(test_cache_short) + np.mean(test_cache_long)))
        # test_results['custom_loss'].append(custom_loss(count, current_pnl, fixed_params['make_profit_margin'], test_results['def_ret'][-1]))

        iteration += 1
        # df_top_combs.to_pickle(STORAGE_PATH + "martin/df_top_combs.pkl")
    date = str(datetime.now().date())
    filename = _INSTRUMENT + "_" + str(_CLUSTER_SIZE) + "_" + str(_FEES) + "_" + str(_TOP_K) + "_" + str(_TRAIN_DAYS)
    pickle.dump(test_results, open(STORAGE_PATH + f"calib_results/{_DIR_PATH}/calibration_results_{filename}.pkl", 'wb'))
    result_df = pd.DataFrame({'X': test_results['parameters'], 'closing_params': test_results['closing_params'], 'pnl': test_results['pnl'], 'count': test_results['count']})
    print(result_df)
    obj_f = result_df['pnl'].sum() / result_df['count'].sum()
    print(obj_f)