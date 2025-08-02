# -*- coding: utf-8 -*-
"""
Created on Mon Jul 29 12:23:02 2024

@author: scasny
"""

import numpy as np
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
import concurrent
from sklearn.metrics import confusion_matrix
from multiprocessing import Pool, cpu_count
import time
import itertools


def custom_loss_numpy(preds, targets, profit_weight=1.0, loss_weight=1.0, fn_penalty=1.0):
    """
    Custom loss function using NumPy for calculations.
    
    Parameters:
    - outputs: Predicted outputs (numpy array of probabilities or logits).
    - targets: Actual target labels (numpy array of binary labels).
    - profit_weight: Weight for the profit term.
    - loss_weight: Weight for the loss term.
    - fn_penalty: Penalty for false negatives.
    
    Returns:
    - total_loss: Calculated custom loss.
    """
    
    # Convert outputs to predicted classes
    predicted_classes = preds
    
    # Identify true positives, false positives, and false negatives
    true_positives = (predicted_classes == 1) & (targets == 1)
    false_positives = (predicted_classes == 1) & (targets == 0)
    false_negatives = (predicted_classes == 0) & (targets == 1)
    
    # Precision calculation
    tp_sum = np.sum(true_positives).astype(float)
    fp_sum = np.sum(false_positives).astype(float)
    fn_sum = np.sum(false_negatives).astype(float)
    
    # If no positive predictions, set precision to 0 to avoid division by zero
    precision = tp_sum / (tp_sum + fp_sum + 1e-10)
    
    # Profit and loss calculation based on precision
    profit = precision * tp_sum * profit_weight
    loss = (1 - precision) * fp_sum * loss_weight
    
    # Additional penalty for false negatives
    penalty = fn_sum * fn_penalty
    
    total_loss = -(profit - loss) + penalty
    if tp_sum + fp_sum < 1:
        return 9999.0
    else:
        return total_loss

def get_preds(df, thold_list, increase_list):
    # Initialize result as a boolean Series with True for all rows
    result = pd.Series(True, index=df.index)
    
    for col, thold, inc in zip(df.columns.tolist(), thold_list, increase_list):
        # Update result by applying condition for each column
        if inc:
            result = result & (df[col] > thold)
        else:
            result = result & (df[col] < thold)
    
    # Convert boolean Series to integer array
    return np.array(result.astype(int))

def calc_combination(df_data, y_col, columns, keys, combination, feature_increase):
    combination_dict = dict(zip(keys, combination))
    list_values = list(combination_dict.values())

    preds = get_preds(df_data[columns], list_values, feature_increase)
    loss = custom_loss_numpy(preds ,df_data[y_col], profit_weight=0.2, loss_weight=0.3, fn_penalty=0.0)

    cm = confusion_matrix(df_data[y_col], preds)
    
    long_TP = cm[1, 1]
    long_FP = cm[0, 1] 

#     short_TP = cm[0, 0]
#     short_FP = cm[1, 0] + cm[2, 0]

    long_count = long_TP + long_FP
    long_precision = long_TP / long_count if long_count > 0 else 0

    return {
        str(list_values): [loss, long_precision, long_count]
    }

feature_bins = {
    # 'trd_gap': [0.1, -0.05, -0.07, -0.09, -0.12, -0.14],
    'int': [0.0, 1.0, 2.5, 3.0, 3.5, 4.0],
    'a_price_sparsity': [-1, 0.1, 0.15, 0.2, .25, .3, 0.4, 0.5],
    'b_price_sparsity': [0.0, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, .25, .3],
    'sparsity_diff': [-1.5, -0.5, 0.0, 0.35, 0.5,  0.75, 0.9]
}
feature_increase = [True, True, False, True]



if __name__ == "__main__":
    columns = list(feature_bins.keys())
    df_data = pd.read_pickle("reg_data_sp_scaled.pkl")[['b_price', 'a_price',
        'trd_gap', 'ba_volrat_30', 'int', '_far_level',
        '_close_level', 'a_price_sparsity', 'b_price_sparsity', 'scaled_sparsity', 'sparsity_diff'
        , 'p_movement_0.3', 'p_movement_1.0', 'y_0.0', 'y_0.15', 'y_0.30']]
    df_data = df_data.dropna(subset=['_close_level', 'int'])
    l_long_relabel = lambda x: 1 if x > 0 else 0
    l_short_relabel = lambda x: 1 if x < 0 else 0
    df_data['y_long'] = df_data['y_0.15'].apply(l_long_relabel)
    df_data['y_short'] = df_data['y_0.15'].apply(l_short_relabel)
    df_data['ba_spread'] = df_data['a_price'] - df_data['b_price']
    df_data['abs_sparsity_diff'] = abs(df_data['sparsity_diff'])
    
    # y_col = 'y_long'
    # columns = list(feature_bins.keys())
    # # Get keys and corresponding bin ranges
    # keys, bin_ranges = zip(*feature_bins.items())

    # # Generate all possible combinations of bins
    # combinations = list(itertools.product(*bin_ranges))
    # pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")
    # score_dict = {}
    
    # # calc_combination(df_data, y_col, columns, keys, combinations[0], feature_increase)

    # with Pool(processes=14) as pool:
    #     async_results = [pool.apply_async(calc_combination, args=(
    #         df_data.copy(), y_col, columns, keys, combination, feature_increase, )) for combination in combinations]

    #     # Periodically check progress and update the progress counter
    #     last_c = 0
    #     while True:
    #         completed = sum(1 for res in async_results if res.ready())
    #         diff_c = completed - last_c
    #         last_c = completed
    #         if diff_c > 0:
    #             pbar.update(diff_c)

    #         if completed == len(async_results):
    #             break
    #         time.sleep(.1)
    #     # Close the pool and wait for the tasks to complete
    #     pool.close()
    #     pool.join()

    #     # Collect results from the AsyncResult objects
    #     for async_result in async_results:
    #         score_dict.update(async_result.get())
    # # COUNTER_ += len(params_dict_list['strt'])
    # pbar.close()
    
    # result = pd.DataFrame({'comb': score_dict.keys(), 
    #           'loss': np.array([*score_dict.values()])[:,0],
    #           'precision': np.array([*score_dict.values()])[:, 1],
    #           'count': np.array([*score_dict.values()])[:, 2]}).sort_values('loss')
    
    

def get_proba(df, comb, increase_list):
    def eval_comb(thold):
        result = True
        thold = list(map(float, thold[1:-1].split(',')))
        for c, th, inc in zip(comb, thold, increase_list):
            result &= (lambda x, thold, inc: x > thold if inc else x < thold
                           )(c, th, inc)
        return result
    
    def get_quantile_for_comb(df):
        length = len(df)
        for i, row in enumerate(df.sort_values('loss', ascending=True).to_dict(orient='records')):
            if eval_comb(row['comb']):
                return (length - i)/length
        return 0.0
    
    return get_quantile_for_comb(df)

# long
sub_space = df_data[
    (df_data['scaled_sparsity'] > 0.85)
    # (df_data['p_movement_0.3'] > 0.05) &
    # (df_data['_far_level'] > 0.8) &
    # (df_data['int'] > 1.5)
].copy()
# short
# sub_space = df_data[
#     # (df_data['scaled_sparsity'] < -0.4) &
#     # (df_data['p_movement_0.3'] < -0.05) &
#     # (df_data['_far_level'] < 0.4) &
#     (df_data['int'] > 1)
# ].copy()
# sub_space = df_data.copy()
import matplotlib.pyplot as plt
_, ax = plt.subplots(2, 1, figsize=[4 ,8], sharex=True)
x = np.round(np.arange(-0.01, 1.0, 0.01), 2)
inspecting_column = 'abs_sparsity_diff'
inspecting_label = 'y_long'
y = [sub_space[sub_space[inspecting_column] > alfa][inspecting_label].mean() for alfa in x]
y_counts = [sub_space[sub_space[inspecting_column] > alfa][inspecting_label].shape[0] for alfa in x]
ax[0].plot(x, y)
ax[0].axhline(y=sub_space[inspecting_label].mean(), lw=2, ls="--", color='k')
ax[1].plot(x, y_counts)
aa = pd.DataFrame({'index': x, 'precision': y, 'count': y_counts})
# bb  = sub_space[sub_space['ba_spread'] < 0.06]