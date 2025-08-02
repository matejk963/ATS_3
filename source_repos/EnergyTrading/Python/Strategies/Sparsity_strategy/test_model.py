from model_class import HierarchyModel
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

import warnings
warnings.filterwarnings('ignore')

### ----------------------------------------------------------------------
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
xgb_config = {
    'max_depth': 2,
    'n_estimators': 10,
    'scale_pos_weight': 1,
    'learning_rate': 0.1
}
#INFO: 1 level model
config_model_dict = {
    "xgb_short": {
        "features": ['scaled_sparsity',
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
                'iterm_spXbavol',
                'diff_am_wm_00',
                'delta_mw_00_05',
                'delta_mw_00_20',],
        "target": 'y_short',
        "config": xgb_config
    },
    "xgb_neu": {
        "features": ['scaled_sparsity',
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
                'iterm_spXbavol',
                'diff_am_wm_00',
                'delta_mw_00_05',
                'delta_mw_00_20',],
        "target": 'y_neu',
        "config": xgb_config
    },
    "xgb_long": {
        "features": ['scaled_sparsity',
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
                'iterm_spXbavol',
                'diff_am_wm_00',
                'delta_mw_00_05',
                'delta_mw_00_20',],
        "target": 'y_long',
        "config": xgb_config
    },
    "thold_func": {
        "args": [0.5, 0.35],
        "kwargs": {}
    }
}



hierarchy.load_hierarchy(dag, config_model_dict, 67)
# fit hierarchy np.stack output -> next layer
# backtest train test split by dates
# loop fit predict
# predict c
# reset stats
# stats for hierarchy model and individual models
# cm stats should be indexed by testing dates
# \

# dataset prep
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
                'iterm_spXbavol',
                'diff_am_wm_00',
                'delta_mw_00_05',
                'delta_mw_00_20',]

y_cols = [
    'y_long',
    'y_short',
    'y_neu',
    'y_comb'
]

df_data = pickle.load(open(r"Z:\data_factory\obt_reg_qmy.pkl", "rb")).reset_index(names=['timestamp'])
df_data['sparsity_diff'] = df_data['scaled_sparsity'].diff(1)
df_data['ba_spread'] = df_data['a_price'] - df_data['b_price']
df_data = df_data[(df_data['sparsity_diff'] > 0.3) & (df_data['ba_spread'] < 0.11)]
# df_data = df_data[(df_data['trd_gap'] >= 0.02)]
# df_data = df_data[df_data['trd_gap'] <= 0.15]
# df_data = df_data.sample(10000)
l_long_relabel = lambda x: 1 if x > 0 else 0
l_short_relabel = lambda x: 1 if x < 0 else 0
l_neu_relabel = lambda x: 1 if x < 0.5 and x > -0.5 else 0
l_relabel_comb = lambda x: 2 if x > 0.5 else 0 if x < -0.5 else 1
y_col = 'y_0.25'
df_data['y_long'] = df_data[y_col].apply(l_long_relabel)
df_data['y_short'] = df_data[y_col].apply(l_short_relabel)
df_data['y_neu'] = df_data[y_col].apply(l_neu_relabel)
df_data['y_comb'] = df_data[y_col].apply(l_relabel_comb)

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

train_days = 10
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

# hierarchy.fit(data_set[0])
# pd.Series(hierarchy.predict(data_set[0]['X_test'])).plot()

# predict 
# output_list & true labels -> calc_cm for model and hierarchy
# \


train_cm = []
test_cm = []

models_train = {k: [] for k in hierarchy.model_layer.keys()}
models_test = {k: [] for k in hierarchy.model_layer.keys()}
feature_imp = {k: [] for k in hierarchy.model_layer.keys()}
idxs = []
preds = []

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
    _ = [feature_imp[m].append(hierarchy.model_layer[m].feature_importance()) for m in hierarchy.model_layer.keys()]

    idxs.extend(data['X_test'].index.values)
    preds.extend(test_preds)

# Overall precsion, box plot with long short precision

def plot_stats(train_cm, test_cm, models_train, plot_models=True, plot_hdi=True):
    import matplotlib.pyplot as plt
    import seaborn as sns
    import arviz as az
    az.rcParams["stats.ci_prob"] = 0.8
    print(df_data[y_col].value_counts()/df_data[y_col].value_counts().sum())
    # Example data (replace with actual data)
    portion_train = [(lambda x: x[:, 2].sum()/(x[:, 0].sum()+x[:, 2].sum()))(m) for m in train_cm]
    portion_test = [(lambda x: x[:, 2].sum()/(x[:, 0].sum()+x[:, 2].sum()))(m) for m in test_cm]

    # Sum for each day
    sum_train = [m[:, 2].sum() + m[:, 0].sum() for m in train_cm]
    sum_test = [m[:, 2].sum() + m[:, 0].sum() for m in test_cm]

    # overall train precision
    train_overall_precision = [(m[0,0]+m[2,2])/(m[:, 2].sum() + m[:, 0].sum()) for m in train_cm]
    train_long_precision = [(m[2,2])/(m[:, 2].sum()) for m in train_cm]
    train_short_precision = [(m[0,0])/(m[:, 0].sum()) for m in train_cm]

    # overall test precision
    test_overall_precision = [(m[0,0]+m[2,2])/(m[:, 2].sum() + m[:, 0].sum()) for m in test_cm]
    test_long_precision = [(m[2,2])/(m[:, 2].sum()) for m in test_cm]
    test_short_precision = [(m[0,0])/(m[:, 0].sum()) for m in test_cm]

    daily_test_precision = [ m for m in test_cm]
    # Create a figure with 3 subplots (1 line plot, 2 bar plots), sharing x-axis
    fig, axs = plt.subplots(5, 1, sharex=True, figsize=(10, 16))

    # Line plot for portion
    days = range(len(portion_train))
    axs[0].plot(days, portion_train, label='Portion Train', color='blue', marker='o')
    axs[0].plot(days, portion_test, label='Portion Test', color='orange', marker='o')
    axs[0].set_title("Portion")
    axs[0].set_ylabel('Portion')
    axs[0].legend()

    # Bar plot for sum_train in the second subplot
    axs[1].bar(days, sum_train, color='blue', alpha=0.6)
    axs[1].set_title('Sum Train')
    axs[1].set_ylabel('Sum Train')

    # Bar plot for sum_test in the third subplot
    axs[2].bar(days, sum_test, color='orange', alpha=0.6)
    axs[2].set_title('Sum Test')
    axs[2].set_ylabel('Sum Test')
    axs[2].set_xlabel('Day')
    axs[2].axhline(np.mean(sum_test))

    axs[3].plot(days, train_overall_precision, label='Overall precision', color='blue', marker='o')
    axs[3].plot(days, train_long_precision, label='Long precision', color='green', marker='o')
    axs[3].plot(days, train_short_precision, label='Short precision', color='red', marker='o')
    axs[3].axhline(pd.Series(train_overall_precision).mean())

    axs[3].set_title("Train precision")
    axs[3].set_ylabel('Train precision in %')
    axs[3].legend()

    axs[4].plot(days, test_overall_precision, label='Overall precision', color='blue', marker='o')
    axs[4].plot(days, test_long_precision, label='Long precision', color='green', marker='o')
    axs[4].plot(days, test_short_precision, label='Short precision', color='red', marker='o')
    axs[4].axhline(pd.Series(test_overall_precision).mean())

    axs[4].set_title("Test precision")
    axs[4].set_ylabel('Test precision in %')
    axs[4].legend()
    print("Test precision", pd.Series(test_overall_precision).mean())

    # Adjust layout
    # plt.tight_layout()

    # Show plot
    plt.show()

    if plot_models:
        for key in hierarchy.model_layer.keys():
            model_score = np.concatenate(models_train[key])
            labels = np.concatenate(
                [x['y_train'][config_model_dict[key]['target']] for x in data_set])
            plt.figure(figsize=(8, 6))
            sns.violinplot(x=labels, y=model_score)
            plt.title(f"Model {key}")
            plt.xlabel('True Label')
            plt.ylabel('Predicted Score (Probability)')
            plt.grid(True)
            plt.show()
            
            values = feature_imp[key]  # numpy array of feature importances for the current model
            feats = config_model_dict[key]['features']  # List of feature names for the current model
            values = np.array(values)  # Shape (41, 12)
            feats = np.array(feats)    # Shape (12,)

            # Create a DataFrame for easy plotting with seaborn
            data = pd.DataFrame(values, columns=feats)

            # Melt the DataFrame to convert it to long format suitable for seaborn boxplot
            data_melted = data.melt(var_name='Feature', value_name='Importance')

            # Plotting the boxplot for each feature
            plt.figure(figsize=(12, 8))
            sns.boxplot(x='Feature', y='Importance', data=data_melted)
            plt.title(f"Model {key}")
            plt.xlabel('Feature Names')
            plt.ylabel('Importance')
            plt.xticks(rotation=45, ha='right')
            plt.grid(axis='y')
            plt.tight_layout()
            plt.show()

    if plot_hdi:
        week_precs = np.array([(lambda m: (m[0,0]+m[2,2])/(m[:, 2].sum() + m[:, 0].sum())
        )(np.sum(test_cm[i:i+5], axis=0)) for i in range(0, len(test_cm), 5)])
        week_precs = week_precs[~np.isnan(week_precs)]
        plt.figure()
        plt.title("5day precision HDI")
        plt.scatter(x=week_precs, y=np.ones(len(week_precs)), alpha=0.5)
        hdi = az.hdi(np.array(week_precs))
        plt.axvline(hdi[0], linestyle="--", linewidth=2)
        plt.axvline(hdi[1], linestyle="--", linewidth=2)
        plt.axvline(np.mean(week_precs), linestyle="-.", color="black")
        # plt.xlim(left=0.0, right=1.0)
        plt.show()
    
    high_vol_idxs = [i for i in range(len(sum_train)) if sum_train[i] > 100]
    day_precs = np.array([(lambda m: (m[0,0]+m[2,2])/(m[:, 2].sum() + m[:, 0].sum())
    )(test_cm[i]) for i in high_vol_idxs])
    day_precs = day_precs[~np.isnan(day_precs)]
    plt.figure()
    plt.title("day precision HDI")
    plt.scatter(x=day_precs, y=np.ones(len(day_precs)), alpha=0.5)
    hdi = az.hdi(np.array(week_precs))
    plt.axvline(hdi[0], linestyle="--", linewidth=2)
    plt.axvline(hdi[1], linestyle="--", linewidth=2)
    plt.axvline(np.mean(day_precs), linestyle="-.", color="black")
    # plt.xlim(left=0.0, right=1.0)
    plt.show()

plot_stats(train_cm, test_cm, models_train=models_train, plot_models=False)


#INFO: ON backtest dataset where model hat is not nan concat with backtest data


for key in hierarchy.model_layer.keys():
    df_data.at[idxs, key] = np.concatenate(models_test[key])

df_data.at[idxs, 'output_y_hat'] = preds

def save(mins, target, threshold):
    df_backtest = pd.read_pickle(r"W:\data_factory\backtest_obt_lead_ttf_lag_de_1.pkl")
    df_backtest = df_backtest[df_backtest.index.date >= df_data['timestamp'].dt.date.unique()[0]]
    df_backtest = df_backtest[['ba_spread', 'b_price', 'a_price', 'mid_price', 'b_vol', 'a_vol',
        'mid', 'scaled_sparsity', 'trd_price', 'bid_t1',
        'ask_t1']]
    df_backtest_model = pd.concat([df_backtest, df_data.set_index('timestamp')[['output_y_hat', 'xgb_long', 'xgb_neu', 'xgb_short']]], axis=1)
    filename = f'data_backtest_q_model_{mins}_{target}_{threshold}.pkl'
    df_backtest_model.to_pickle(filename)
    print(filename)


# h_raw = HierarchyModel()
# hierarchy.export_hierarchy()
# h_raw.load_raw("hierarchy_dump.json")