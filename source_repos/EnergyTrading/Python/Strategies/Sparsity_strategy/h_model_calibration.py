import networkx as nx
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.preprocessing import StandardScaler, PowerTransformer
from sklearn.linear_model import LinearRegression
from xgboost import XGBClassifier
import xgboost as xgb
import pickle
from sklearn.metrics import confusion_matrix
import pandas as pd
import numpy as np
import itertools
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
import math
import time
import pickle

import warnings
warnings.filterwarnings('ignore')

# local imports
from model_class import HierarchyModel

### ----------------------------------------------------------------------

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




# Overall precsion, box plot with long short precision
def calibration_step(static_data, MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST):
    def custom_metric(precision, count, min_tp_threshold, beta_pos=0.4, beta_neg=0.35):
        # Precision reward and false positive penalty
        score = count * (precision * beta_pos - (1 - precision) * beta_neg)
        
        # Apply a stronger penalty if the count is below the threshold
        if count < min_tp_threshold:
            penalty_scale = (min_tp_threshold - count) / min_tp_threshold
            score -= penalty_scale * count  # Stronger penalty by multiplying the count deficit
        
        return score
    
    data_set = static_data['data_set']
    feature_cols = static_data['feature_cols']

    hierarchy = HierarchyModel()
    # Define a sample DAG
    dag = nx.DiGraph()

    # Add edges and associate each node with a unique name and a function name
    dag.add_node("xgb_short", func_name="xgb")
    dag.add_node("xgb_neu", func_name="xgb")
    dag.add_node("xgb_long", func_name="xgb")
    dag.add_node("thold_func", func_name="thold_func")

    # Add edges between nodes
    dag.add_edges_from([
        ("xgb_short", "thold_func"),
        ("xgb_neu", "thold_func"),
        ("xgb_long", "thold_func")
    ])

    config_model_dict = {
        "xgb_short": {
            "features": feature_cols,
            "target": 'y_short',
            "config": {
                'max_depth': MAX_DEPTH,
                'n_estimators': N_TREES
            }
        },
        "xgb_neu": {
            "features": feature_cols,
            "target": 'y_neu',
            "config": {
                'max_depth': MAX_DEPTH,
                'n_estimators': N_TREES
            }
        },
        "xgb_long": {
            "features": feature_cols,
            "target": 'y_long',
            "config": {
                'max_depth': MAX_DEPTH,
                'n_estimators': N_TREES
            }
        },
        "thold_func": {
            "args": [THOLD_FOR, THOLD_AGAINST], #INFO: don't forget 0.6 not 60!!!!
            "kwargs": {}
        }
    }
    hierarchy.load_hierarchy(dag, config_model_dict, 41)
    train_cm = []
    test_cm = []

    models_train = {k: [] for k in hierarchy.model_layer.keys()}
    models_test = {k: [] for k in hierarchy.model_layer.keys()}


    for data in data_set:
        hierarchy.fit(data)
        train_preds = hierarchy.predict(data['X_train'])
        train_outputs = hierarchy.model_outputs
        hierarchy.model_outputs = {}
        train_cm.append(confusion_matrix(data['y_train']['y_comb'], train_preds, labels=[0, 1, 2]))

        test_preds = hierarchy.predict(data['X_test'])
        test_outputs = hierarchy.model_outputs
        hierarchy.model_outputs = {}
        test_cm.append(confusion_matrix(data['y_test']['y_comb'], test_preds, labels=[0, 1, 2]))

        # models stats
        _ = [models_train[m].append(train_outputs[m]) for m in hierarchy.model_layer.keys()]
        _ = [models_test[m].append(test_outputs[m]) for m in hierarchy.model_layer.keys()]

    m = np.array(test_cm).sum(axis=0)
    tp_count = m[0,0]+m[2,2]
    overall_precision = (tp_count)/(m[:, 2].sum() + m[:, 0].sum())
    long_precision = (m[2,2])/(m[:, 2].sum())
    short_precision = (m[0,0])/(m[:, 0].sum())

    score = custom_metric(overall_precision, tp_count, 100)
    return {(MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST): {
        "overall_prec": overall_precision,
        "score": score
        }
    }


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
    # DATA PREP ---------------------------------------
    df_data = pickle.load(open(r"C:\develop\EnergyTrading\Python\Strategies\Sparsity_strategy\obt_reg_qmy.pkl", "rb"))
    df_data['sparsity_diff'] = df_data['scaled_sparsity'].diff(1)
    df_data['ba_spread'] = df_data['a_price'] - df_data['b_price']
    df_data = df_data[(df_data['sparsity_diff'] > 0.3) & (df_data['ba_spread'] < 0.16)]
    # df_data = df_data[(df_data['trd_gap'] >= 0.02)]
    # df_data = df_data[df_data['trd_gap'] <= 0.15]
    # df_data = df_data.sample(10000)
    l_long_relabel = lambda x: 1 if x > 0 else 0
    l_short_relabel = lambda x: 1 if x < 0 else 0
    l_neu_relabel = lambda x: 1 if x < 0.5 and x > -0.5 else 0
    l_relabel_comb = lambda x: 2 if x > 0.5 else 0 if x < -0.5 else 1

    df_data['y_long'] = df_data['y_0.09'].apply(l_long_relabel)
    df_data['y_short'] = df_data['y_0.09'].apply(l_short_relabel)
    df_data['y_neu'] = df_data['y_0.09'].apply(l_neu_relabel)
    df_data['y_comb'] = df_data['y_0.09'].apply(l_relabel_comb)

    y_cols = [
        'y_long',
        'y_short',
        'y_neu',
        'y_comb'
    ]

    days = df_data['day'].unique()
    df_data['iterm_fmXret'] = df_data['lag_return_hat']*df_data['fair_margin']
    df_data['iterm_fmXret'] = abs_max_scale(df_data, 'iterm_fmXret')
    df_data['iterm_spXbavol'] = df_data['scaled_sparsity']*df_data['ba_volrat_50']
    df_data['iterm_spXbavol'] = abs_max_scale(df_data, 'iterm_spXbavol')
    df_data = df_data.dropna(subset=feature_cols)

    def df_days_tag(df):
        unique_dates = df['timestamp'].dt.date.unique()
        
        # Create a dictionary to map unique dates to tags
        date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
        
        # Add a new column for the tags
        df['day'] = df['timestamp'].dt.date.map(date_to_tag)
        
        return df.copy()
    tagged_df = df_days_tag(df_data).copy()

    train_days = 20
    test_days = 1
    step = 1
    max_day = tagged_df.day.max()
    data_set_dict = {range_tuple: {} for range_tuple in [
        (train_start, train_start+(train_days-1), train_start+(train_days+test_days-1)) for train_start in range(
            0, max_day-(train_days+test_days), step)]}
    data_set = []

    for date_tuple in data_set_dict.keys():
        train_range = range(date_tuple[0], date_tuple[1]+1)
        test_range = range(date_tuple[1]+1, date_tuple[2]+1)

        data_set_dict[date_tuple]['train'] = tagged_df[tagged_df['day'].isin(train_range)]
        data_set_dict[date_tuple]['test'] = tagged_df[tagged_df['day'].isin(test_range)]

        data_set_dict[date_tuple]['train'] = tagged_df[tagged_df['day'].isin(train_range)]
        data_set_dict[date_tuple]['test'] = tagged_df[tagged_df['day'].isin(test_range)]
        data_set.append(
            {
                'X_train': tagged_df[tagged_df['day'].isin(train_range)][feature_cols],
                'y_train': tagged_df[tagged_df['day'].isin(train_range)][y_cols],
                'X_test': tagged_df[tagged_df['day'].isin(test_range)][feature_cols],
                'y_test': tagged_df[tagged_df['day'].isin(test_range)][y_cols]
            }
        )
    
    # --------------------------------------------\
    MAX_DEPTH = [2, 3, 4, 5]
    N_TREES = [3, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 50, 100]  
    THOLD_FOR = [.45, .50, .52, .55, .57, .60, .62, .65, .67, .70, .72, .75]
    THOLD_AGAINST = [.0, .10, .15, .20, .25, .30, .35, .40, .45]
    # TEST
    MAX_DEPTH = [2]
    N_TREES = [30]  
    THOLD_FOR = [.30]
    THOLD_AGAINST = [.0]

    static_data = {'data_set': data_set, 'feature_cols': feature_cols}

    combinations = list(itertools.product(MAX_DEPTH, N_TREES, THOLD_FOR, THOLD_AGAINST))
    result = {}
    score_dict = {k: -420 for k in combinations}

    pbar = tqdm(total=len(combinations), desc="Instr Combo Progress")

    static_data = {
        'data_set': data_set, 
        'feature_cols': feature_cols}
    
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

    print(score_dict)