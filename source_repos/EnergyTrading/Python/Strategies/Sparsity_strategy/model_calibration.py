# -*- coding: utf-8 -*-
"""
Created on Tue May 28 18:01:52 2024

@author: scasny
"""

import pandas as pd
from xgboost import XGBClassifier
from scipy.stats import percentileofscore
import numpy as np
from sklearn.metrics import confusion_matrix
import itertools
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
import math
import time
import pickle


def calibration_step(static_data, MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST, SUBSAMPLE, COLSAMPLE, GAMMA, MIN_CH, LAMBDA, ETA):
    def idx_max_thold(array, thold_for, thold_against):
        new_array = np.array(array)/sum(array)
        best, sbest = sorted([(v, i) for i, v in enumerate(new_array)], reverse=True)[:2]
        b_sb_diff = best[0] - sbest[0]
        return best[1] if (array[best[1]] > thold_for) and (b_sb_diff > thold_against) else 1
    
    def expected_value(precision, count):
        PROFIT_ = 0.2
        LOSS_ = 0.35
        return (count*precision*PROFIT_)-(count*(1-precision)*LOSS_)
    
    xx = {}
    heatmap = np.zeros((3,3))
    data_set_dict = static_data['data_set_dict']
    feature_cols = static_data['feature_cols']
    l_long_relabel = lambda x: 1 if x > 0 else 0
    l_short_relabel = lambda x: 1 if x < 0 else 0
    l_neu_relabel = lambda x: 1 if x < 0.5 and x > -0.5 else 0
    l_relabel_comb = lambda x: 2 if x > 0.5 else 0 if x < -0.5 else 1
    
    for key, data in data_set_dict.items():
        train = data['train'].copy()
        test = data['test'].copy()

        xgb_model_long = XGBClassifier(objective='binary:logistic', max_depth=MAX_DEPTH, n_estimators=N_TREES, subsample=SUBSAMPLE, colsample_bytree=COLSAMPLE,
                                    gamma=GAMMA, min_child_weight=MIN_CH, reg_lambda=LAMBDA, learning_rate=ETA)
        xgb_model_long.fit(train[feature_cols],
                    train['y_0.09'].apply(l_long_relabel))

        preds_long = xgb_model_long.predict_proba(test[feature_cols])[:,1]

        xgb_model_short = XGBClassifier(objective='binary:logistic', max_depth=MAX_DEPTH, n_estimators=N_TREES, subsample=SUBSAMPLE, colsample_bytree=COLSAMPLE,
                                    gamma=GAMMA, min_child_weight=MIN_CH, reg_lambda=LAMBDA, learning_rate=ETA)
        xgb_model_short.fit(train[feature_cols],
                    train['y_0.09'].apply(l_short_relabel))

        preds_short = xgb_model_short.predict_proba(test[feature_cols])[:,1]

        xgb_model_neu = XGBClassifier(objective='binary:logistic', max_depth=MAX_DEPTH, n_estimators=N_TREES, subsample=SUBSAMPLE, colsample_bytree=COLSAMPLE,
                                    gamma=GAMMA, min_child_weight=MIN_CH, reg_lambda=LAMBDA, learning_rate=ETA)
        xgb_model_neu.fit(train[feature_cols],
                    train['y_0.09'].apply(l_neu_relabel))

        preds_neu = xgb_model_neu.predict_proba(test[feature_cols])[:,1]

        preds_comb = np.stack((preds_short, preds_neu, preds_long), axis=1)

        result = {'p_short': [], 'p_neu': [], 'p_long': [],'count': [], 'count_short': [],'count_long': [], 'ev': [], 'w_p': []}

        preds = [idx_max_thold(x, THOLD_FOR, THOLD_AGAINST) for x in preds_comb]
        cm = confusion_matrix(test['y_0.09'].apply(l_relabel_comb), preds, labels=[0, 1, 2])
        
        long_TP = cm[2, 2]  # Actual positive (1) and predicted positive (1)
        long_FP = cm[0, 2] + cm[1, 2] # Actual negative (0) but predicted positive (1)

        short_TP = cm[0, 0]  # Actual positive (1) and predicted positive (1)
        short_FP = cm[1, 0] + cm[2, 0] # Actual negative (0) but predicted positive (1)

        neu_TP = cm[1, 1]  # Actual positive (1) and predicted positive (1)
        neu_FP = cm[0, 1] + cm[2, 1] # Actual negative (0) but predicted positive (1)
        
        long_count = long_TP + long_FP
        short_count = short_TP + short_FP
        long_precision = long_TP / long_count if long_count > 0 else 0
        short_precision = short_TP / short_count if short_count > 0 else 0
        neu_precision = neu_TP / (neu_TP + neu_FP) if (neu_TP + neu_FP) > 0 else 0


        result['p_short'].append(short_precision)
        result['p_neu'].append(neu_precision)
        result['p_long'].append(long_precision)
        result['count_short'].append(short_count)
        result['count_long'].append(long_count)
        result['count'].append(long_count+short_count)

        ev = expected_value(long_precision, long_count ) + expected_value(short_precision, short_count)
        result['ev'].append(ev)
        
        result['w_p'].append((long_precision*long_count + short_precision*short_count)/(long_count+short_count) if (long_count+short_count) > 0 else 0)
        

        df_max = pd.DataFrame(result)
        df_max = df_max.iloc[df_max['ev'].idxmax()].to_dict()
        xx[key] = df_max
        heatmap += cm
    df_res = pd.DataFrame(xx).T
    df_res['count_wp'] = df_res['count']*df_res['w_p']

    return {(MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST, SUBSAMPLE, COLSAMPLE, GAMMA, MIN_CH, LAMBDA, ETA): {
        "daily_p": df_res[df_res['count'] > 0]['w_p'].mean(),
        "general_p": (df_res['count_wp'].sum()/df_res['count'].sum()),
        "ev": df_res['ev'].sum(),
        "avg_count": df_res['count'].mean(),
        "active_days": sum(df_res['count'] > 0)}
        }

def abs_max_scale(df, column_name):
    """
    Rescale the specified column in the DataFrame using Min-Max scaling,
    keeping negative values intact by scaling between the min and max of the column.

    Parameters:
    df (pd.DataFrame): The DataFrame containing the column to scale.
    column_name (str): The name of the column to be scaled.

    Returns:
    pd.Series: The scaled column as a Pandas Series.
    """
    min_val = df[column_name].min()
    max_val = df[column_name].max()

    # Min-Max Scaling considering the entire range (including negatives)
    scaled_column = df[column_name]/max(abs(min_val), abs(max_val))
    
    return scaled_column

def df_days_tag(df):
    unique_dates = df['timestamp'].dt.date.unique()
    
    # Create a dictionary to map unique dates to tags
    date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
    
    # Add a new column for the tags
    df['day'] = df['timestamp'].dt.date.map(date_to_tag)
    
    return df.copy()

if __name__ == "__main__":
    # -----------------------------------------------------------------
    feature_cols = ['scaled_sparsity',
                    'fair_margin',
                    'lag_return_hat',
                    '_close_level',
                    '_far_level',
                    'ba_volrat_00',
                    'ba_volrat_50',
                    'p_movement_0.5',
                    'a_price_sparsity',
                    'b_price_sparsity',
                    'iterm_fmXret',
                    'iterm_spXbavol']
    # -----------------------------------------------------------------
    
    # load data
    df_data = pickle.load(open(r"Z:\Algo_data\obt_reg_qmy.pkl", "rb"))
    df_data['sparsity_diff'] = df_data['scaled_sparsity'].diff(1)
    df_data['ba_spread'] = df_data['a_price'] - df_data['b_price']
    df_data = df_data[(df_data['sparsity_diff'] > 0.3) & (df_data['ba_spread'] < 0.16)]
    # df_data = df_data[(df_data['trd_gap'] >= 0.02)]
    # df_data = df_data[df_data['trd_gap'] <= 0.15]
    # df_data = df_data.sample(10000)
    l_long_relabel = lambda x: 1 if x > 0 else 0
    l_short_relabel = lambda x: 1 if x < 0 else 0
    l_relabel_comb = lambda x: 2 if x > 0.5 else 0 if x < -0.5 else 1
    
    df_data['y_long'] = df_data['y_0.09'].apply(l_long_relabel)
    df_data['y_short'] = df_data['y_0.09'].apply(l_short_relabel)
    df_data['iterm_fmXret'] = df_data['lag_return_hat']*df_data['fair_margin']
    df_data['iterm_fmXret'] = abs_max_scale(df_data, 'iterm_fmXret')
    df_data['iterm_spXbavol'] = df_data['scaled_sparsity']*df_data['ba_volrat_50']
    df_data['iterm_spXbavol'] = abs_max_scale(df_data, 'iterm_spXbavol')
    df_data = df_data.dropna(subset=feature_cols)

    tagged_df = df_days_tag(df_data).copy()    

    train_days = 20
    test_days = 1
    step = 1
    max_day = tagged_df.day.max()
    data_set_dict = {range_tuple: {} for range_tuple in [
        (train_start, train_start+(train_days-1), train_start+(train_days+test_days-1)) for train_start in range(
            0, max_day-(train_days+test_days), step)]}
    for date_tuple in data_set_dict.keys():
        train_range = range(date_tuple[0], date_tuple[1]+1)
        test_range = range(date_tuple[1]+1, date_tuple[2]+1)

        data_set_dict[date_tuple]['train'] = tagged_df[tagged_df['day'].isin(train_range)]
        data_set_dict[date_tuple]['test'] = tagged_df[tagged_df['day'].isin(test_range)]


    MAX_DEPTH = [2, 3, 4]
    N_TREES = [5, 7, 10, 15, 20, 30, 50]
    THOLD_FOR = [50, 52, 55, 57, 60, 62, 65, 67, 70]
    THOLD_AGAINST = [0, 10, 15, 20, 25, 30, 35, 40, 45]
    SUBSAMPLE = [1]
    COLSAMPLE = [1]
    GAMMA = [0]
    MIN_CH = [0]
    LAMBDA = [0, 1, 2]
    ETA = [0.3, 0.25, 0.2, 0.17, 0.15, 0.12, 0.1, 0.07, 0.05]   
    
    # TEST
    MAX_DEPTH = [2]
    N_TREES = [5]
    THOLD_FOR = [50, 52, 55, 57, 60]
    THOLD_AGAINST = [0]
    SUBSAMPLE = [1]
    COLSAMPLE = [1]
    GAMMA = [0]
    MIN_CH = [0]
    LAMBDA = [0]
    ETA = [0.3]   

    combinations = list(itertools.product(MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST, SUBSAMPLE, COLSAMPLE, GAMMA, MIN_CH, LAMBDA, ETA))
    result = {}
    score_dict = {k: 0 for k in combinations}

    pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")

    static_data = {'data_set_dict': data_set_dict, 'feature_cols': feature_cols}
    
    cpu_percent = 80
    
    total_cores = cpu_count()
    # Ensure at least 2 cores are reserved for the system
    usable_cores = max(2, total_cores - 2) 
    # Calculate cores based on the specified percentage, rounding down but ensuring at least 1 core is used
    cores_to_use = max(1, min(math.floor(usable_cores * (cpu_percent / 100.0)), usable_cores))


    with Pool(processes=cores_to_use) as pool:
        async_results = [pool.apply_async(calibration_step, args=(static_data, *params_dict, )) for params_dict in combinations]

        # Periodically check progress and update the progress counter
        last_c = 0
        while True:
            completed = sum(1 for res in async_results if res.ready())
            diff_c = completed - last_c
            last_c = completed
            if diff_c > 0:
                pbar.update(diff_c)

            if completed == len(async_results):
                break
            time.sleep(.1)
        # Close the pool and wait for the tasks to complete
        pool.close()
        pool.join()

        # Collect results from the AsyncResult objects
        for async_result in async_results:
            score_dict.update(async_result.get())
    pbar.close()