# -*- coding: utf-8 -*-
"""
Created on Mon Jan 20 10:50:24 2025

@author: scasny
"""
import pandas as pd
import torch
import numpy as np
import heapq
from tqdm import tqdm
import psutil
import os 
from torch.profiler import profile, ProfilerActivity

from Strategies.Modular_strategy.features_tensor import *
from Utilities.func_utils import execution_time
from Utilities.torch_utils import device_agnostic, TensorTracker, format_bytes

device = device_agnostic(mode='gpu', cpu_threads=30)

num_rows = 20000
data_columns = [
    'a_price_sparsity',
    'b_price_sparsity',
    'scaled_sparsity',
    'int',
    'ba_volrat',
    '_far_level',
    'p_movement_0.3',
    'bid_t1',
    'ask_t1'
]

# Initialize a dictionary to store synthetic data for each column
synthetic_data = {}

# Generate synthetic data for each column based on the specified properties
synthetic_data['a_price_sparsity'] = torch.clamp(
    torch.normal(mean=0.15, std=0.05, size=(num_rows,)), 0, 1
)  # Mean 0.15, range [0, 1]
synthetic_data['b_price_sparsity'] = torch.clamp(
    torch.normal(mean=0.15, std=0.05, size=(num_rows,)), 0, 1
)  # Mean 0.15, range [0, 1]
synthetic_data['scaled_sparsity'] = torch.rand(num_rows)  # Uniformly distributed in [0, 1]
synthetic_data['int'] = torch.rand(num_rows) * 10  # Uniformly distributed in [0, 10]
synthetic_data['ba_volrat'] = torch.clamp(
    torch.normal(mean=0.0, std=0.5, size=(num_rows,)), -1, 1
)  # Mean 0.0, range [-1, 1]
synthetic_data['_far_level'] = torch.rand(num_rows)  # Uniformly distributed in [0, 1]
synthetic_data['p_movement_0.3'] = torch.rand(num_rows)  # Uniformly distributed in [0, 1]
synthetic_data['bid_t1'] = (torch.rand(num_rows) > 0.3).bool() 
synthetic_data['ask_t1'] = (torch.rand(num_rows) < 0.7).bool()

# Combine all columns into a single tensor with shape (num_rows, len(data_columns))
D = torch.stack([synthetic_data[col] for col in data_columns], dim=1).to(device)

features = {
    'FeatureSparsity': {
        'class': FeatureSparsity,
        'th_feat_sp_dense': [0.16, 0.21, 0.26, 0.41, 1.0],
        'th_feat_sp_sparse': [0.0, 0.14, 0.19, 0.24, 0.29, 0.39]
    },
    'FeatureScaledSp': {
        'class': FeatureScaledSp,
        'th_feat_scaled_sp': [-0.1, 0.0, 0.1, 0.2, 0.3, 0.5, 0.6, 0.75, 0.8, 0.9]
    },
    'FeatureFarLevel': {
        'class': FeatureFarLevel,
        'th_feat_far_level': [1.1, 0.9, 0.8, 0.7, 0.5, 0.4,  0.25, 0.1]
    },
    'FeaturePMovement': {
        'class': FeaturePMovement,
        'th_feat_p_movement03': [-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6,  0.7, 0.8, 0.9]}
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
    
thold_tensors = [torch.tensor(sublist, device=device) for sublist in thold_list]
x_shapes = torch.tensor([x.shape[0] for x in thold_tensors], device=device)

tdw = TensorDataWrapper(D, 
                        data_columns, 
                        features_order, 
                        thold_tensors)

# MDX 
# shape (n_rows, x_length)
# dtype:= bool

MDX_short, MDX_long = [], []
for k, v in features.items():
    cls_obj = v['class']
    unpack_list = len(cls_obj.thold_columns) > 1
    
    bool_short = cls_obj.condition_short(tdw)
    bool_long = cls_obj.condition_long(tdw)
    
    MDX_short.extend(bool_short if unpack_list else [bool_short])
    MDX_long.extend(bool_long if unpack_list else [bool_long])


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

def calculate_scores_old(mask, cache_tensors):
    """Calculate normalized scores for combinations with configurable cache dims"""
    # Expand mask dimensions to match cache_tensors
    """Added tensor size debugging"""
    for _ in range(len(cache_dims)):
        mask = mask.unsqueeze(-1)
    
    # Convert mask to same dtype as cache_tensors for multiplication
    mask = mask.to(cache_tensors.dtype)
    
    # Vectorized calculation using broadcasting
    gathered = cache_tensors * mask  # (num_rows, batch_size, *cache_dims)
    
    # Sum over rows and cache dimensions
    sum_dims = (0,) + tuple(range(2, 2 + len(cache_dims)))  # Sum over num_rows and cache dims
    summed = gathered.sum(dim=sum_dims)
    
    # Calculate normalization factor
    divisor = torch.prod(torch.tensor(cache_dims, device=cache_tensors.device))
    
    return summed / divisor

def calculate_scores(mask, cache_tensors):
    """Calculate normalized scores for combinations with configurable cache dims"""
    # Convert mask to same dtype as cache_tensors for multiplication
    mask = mask.to(cache_tensors.dtype)
    
    # Align dimensions for broadcasting
    mask = mask.unsqueeze(-1).unsqueeze(-1)  # Shape [20000, 2048, 1, 1]
    cache_tensors = cache_tensors.unsqueeze(1)  # Shape [20000, 1, 1, 1]
    
    # Vectorized calculation with broadcasting
    gathered = cache_tensors * mask  # Result shape [20000, 2048, 1, 1]
    
    # Sum over batch (dim=0) and cache dimensions (dims=2,3)
    summed = gathered.sum(dim=(0, 2, 3))  # Result shape [2048]
    
    return summed


def update_topk_heap(heap, scores, indices, counter, top_k):
    """Update heap with new batch of scores and indices"""
    for score, idx in zip(scores, indices):
        if score > heap[0][0]:
            # Push new element and pop smallest
            heapq.heappushpop(heap, (score.item(), counter, idx))
            counter += 1
    return counter

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
    pbar = tqdm(total=total_combs, desc="Processing combinations", unit="combo")
    
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



# Modified cache tensor creation
cache_dims = (1, 1)
cache_r = {
    i: np.random.normal(size=cache_dims)
    for i in range(num_rows)
}

cache_tensors = torch.zeros((num_rows, *cache_dims), 
                          device=device, 
                          dtype=torch.float16)

for i, arr in cache_r.items():
    cache_tensors[i] = torch.tensor(arr, dtype=torch.float16, device=device)


# Process and get top combinations
def process_and_intersect(MDX_short, MDX_long, cache_tensors, combs_shape, device, top_k=10000, batch_size=2**12):
    # Process both short and long conditions
    top_short = process_batches_with_topk(
        MDX=MDX_short,
        cache_tensors=cache_tensors,
        combs_shape=combs_shape,
        device=device,
        top_k=top_k,
        batch_size=batch_size
    )

    top_long = process_batches_with_topk(
        MDX=MDX_long,
        cache_tensors=cache_tensors,
        combs_shape=combs_shape,
        device=device,
        top_k=top_k,
        batch_size=batch_size
    )

    # Convert to sets of index tuples for intersection
    def get_index_set(top_list):
        return {tuple(idx.cpu().numpy().tolist()) for score, idx in top_list}

    set_short = get_index_set(top_short)
    set_long = get_index_set(top_long)
    
    # Find intersecting combinations
    intersection = set_short & set_long
    
    # Convert back to tensor indices with preserved order
    return pd.DataFrame(
        [(idx, score) for score, idx in (  # Swap tuple elements
            (s, i) for s, i in top_short 
            if tuple(i.cpu().numpy().tolist()) in intersection
        )],
        columns=['comb', 'score']
    )

# Usage
final_top_combos = process_and_intersect(
    MDX_short=MDX_short,
    MDX_long=MDX_long,
    cache_tensors=cache_tensors,
    combs_shape=x_shapes,
    device=device,
    top_k=10000,
    batch_size=2**11
)