#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 28 11:02:06 2025

@author: marek
"""

import pickle
import numpy as np
import pandas as pd
from datetime import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix


def custom_metric(conf_mat):

    # Define your penalty matrix:
    weights = np.array([
        [ 1.0,   0.0,  -3.0],   # actual class 1
        [-1.0,   0.0,  -1.0],   # actual class 2
        [-3.0,   0.0,   1.0]    # actual class 3
    ])

    # Total score calculation:
    total_score = np.sum(conf_mat * weights)
    if abs(np.sum(conf_mat)) < 1:
        return 0
    else:
        return total_score / np.sum(conf_mat)  # normalized by total predictions


class ModelClass:
    def __init__(self, model, class_list=[-1, 0, 1], thres_list=[.0],
                 gap_mrg=0., gap_bool=False):
        model_class = model.__class__
        model_params = model.get_params(deep=False)
        self.model_dict = {c: model_class(**model_params) for c in class_list}
        self.class_list = class_list
        self.thres_list = thres_list
        self.gap_bool = gap_bool
        self.gap_mrg = gap_mrg
        self.feature_idx_dict = {c: [] for c in class_list}

    def change_model(self, model):
        model_class = model.__class__
        model_params = model.get_params(deep=False)
        self.model_dict = {c: model_class(**model_params) for c in self.class_list}

    @property
    def thres(self):
        return self.thres_list[0]
    
    @property
    def thres_single(self):
        if len(self.thres_list) == 1:
            return None
        else:
            return self.thres_list[1]

    def eval_proba(self, proba_row):
        """
        Evaluate the probability matrix and return the class predictions
        based on the threshold.
        """
        if np.sum(proba_row) > 1e-3:
            proba_row_norm = proba_row / np.sum(proba_row)
        else:
            proba_row_norm = proba_row
        if np.max(proba_row_norm) - np.sort(proba_row_norm)[-2] >= self.thres:
            if self.thres_single is None:
                return True
            else:
                if np.max(proba_row) >= self.thres_single:
                    return True
                else:
                    return False
        else:
            return False

    def feature_importances(self, threshold=0.9):
        all_indices = set()
        for c, m in self.model_dict.items():
            if hasattr(m, 'feature_importances_'):
                # Feature selection based on importances
                importances = m.feature_importances_
                sorted_idx = np.argsort(importances)[::-1]
                sorted_importances = importances[sorted_idx]
                cumsum = np.cumsum(sorted_importances)

                n_keep = np.searchsorted(cumsum, threshold) + 1
                selected = sorted_idx[:n_keep].tolist()
                self.feature_idx_dict[c] = selected
                all_indices.update(selected)
            else:
                # If the model does not have feature importances, keep all features
                self.feature_idx_dict[c] = []
        return list(all_indices)

    def feature_importance_cols(self, col_names):
        """
        Returns a dictionary with class keys and lists of feature names
        corresponding to the selected features based on feature importances.
        """
        feature_names_dict = {}
        for c, idx_list in self.feature_idx_dict.items():
            if idx_list:
                feature_names_dict[c] = [col_names[i] for i in idx_list]
            else:
                feature_names_dict[c] = col_names
        return feature_names_dict

    def fit(self, X, y):
        if self.gap_bool:
            return self.fit_0(X, y)
        else:
            return self.fit_1(X, y)

    def fit_0(self, X, y):
        for c in self.model_dict.keys():
            y_c = (y == c).astype(int)
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[c]:
                X_c = X
            else:
                X_c = X[:, self.feature_idx_dict[c]]
            # Fit the model for class c
            self.model_dict[c].fit(X_c, y_c)
        return 1

    def fit_1(self, X, y):
        """
        • If X[*, -1]  > 0 → fit the model stored under key  1
        • If X[*, -1]  < 0 → fit the model stored under key -1
        (rows in which the last column is exactly zero are ignored)
        The target is turned into a binary flag matching the key,
        mirroring the logic of `fit_0`.
        """
        # rows where the last feature is positive
        pos_mask = X[:, -1] >= self.gap_mrg
        if pos_mask.any():
            y_pos = (y[pos_mask] == 1).astype(int)
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[1]:
                X_pos = X[pos_mask]
            else:
                X_pos = X[pos_mask][:, self.feature_idx_dict[1]]
            # Fit the model for class 1
            self.model_dict[1].fit(X_pos, y_pos)
        # rows where the last feature is negative
        neg_mask = X[:, -1] <= -self.gap_mrg
        if neg_mask.any():
            y_neg = (y[neg_mask] == -1).astype(int)
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[-1]:
                X_neg = X[neg_mask]
            else:
                X_neg = X[neg_mask][:, self.feature_idx_dict[-1]]
            self.model_dict[-1].fit(X_neg, y_neg)
        # Fit neutral class on all data
        if 0 in self.class_list:
            y_neutral = (y == 0).astype(int)
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[0]:
                X_neutral = X
            else:
                X_neutral = X[:, self.feature_idx_dict[0]]
            # Fit the model for class 0
            self.model_dict[0].fit(X_neutral, y_neutral)
        return 1

    def predict_proba(self, X):
        if self.gap_bool:
            return self.predict_proba_0(X)
        else:
            return self.predict_proba_1(X)

    def predict_proba_0(self, X):
        proba_dict = {}
        for c in self.model_dict.keys():
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[c]:
                X_c = X
            else:
                X_c = X[:, self.feature_idx_dict[c]]
            proba_dict[c] = self.model_dict[c].predict_proba(X_c)[:, 1]
        return pd.DataFrame(proba_dict).values

    def predict_proba_1(self, X):
        proba_dict = {k: np.zeros(X.shape[0]) for k in self.class_list}
        pos_mask = X[:, -1] > self.gap_mrg
        neg_mask = X[:, -1] < -self.gap_mrg

        if pos_mask.any():
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[1]:
                X_pos = X[pos_mask]
            else:
                X_pos = X[pos_mask][:, self.feature_idx_dict[1]]
            # Predict probabilities for class 1
            proba_dict[1][pos_mask] = self.model_dict[1].predict_proba(X_pos)[:, 1]
        if neg_mask.any():
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[-1]:
                X_neg = X[neg_mask]
            else:
                X_neg = X[neg_mask][:, self.feature_idx_dict[-1]]
            # Predict probabilities for class -1
            proba_dict[-1][neg_mask] = self.model_dict[-1].predict_proba(X_neg)[:, 1]
        if 0 in self.class_list:
            # Select features based on feature_idx_dict
            if not self.feature_idx_dict[0]:
                X_neutral = X
            else:
                X_neutral = X[:, self.feature_idx_dict[0]]
            # Predict probabilities for class 0
            proba_dict[0] = self.model_dict[0].predict_proba(X_neutral)[:, 1]
        return pd.DataFrame(proba_dict).values

    def predict(self, X):
        proba_mat = self.predict_proba(X)
        class_pred = []
        for p_row in proba_mat:
            # Determine the class based on the threshold
            if self.eval_proba(p_row):
                class_pred.append(self.class_list[np.argmax(p_row)])
            else:
                class_pred.append(0)
        return np.array(class_pred)

    def score(self, y_pred, y_true, func=None):
        def accuracy(mat):
            TN, FP = mat[0, 0], mat[1, 0] + mat[2, 0]
            FN, TP = mat[0, 2] + mat[1, 2], mat[2, 2]
            if (TP + TN + FP + FN) == 0:
                return np.nan
            else:
                return (TP + TN) / (TP + TN + FP + FN)
        conf_mat = confusion_matrix(y_true, y_pred, labels=[-1, 0, 1])
        if func is None:
            return accuracy(conf_mat)
        else:
            return func(conf_mat)


class DataClass:
    def __init__(self, scale_bool):
        self.scale_bool = scale_bool
        self.__scale_params_dict = {}

    @staticmethod
    def split_data(df_data, date_range_dict, n_tests, y_col, x_cols):
        date_s = {k: (v[-n_tests], v[-1]) for k, v in date_range_dict.items()}
        out_dict = {'train': {}, 'tests': {}, 'keys': []}
        y_ser = df_data[y_col]
        X_df = df_data[x_cols]
        for d, date_tuple in date_s.items():
            date_test, date_end = date_tuple
            date_end += pd.Timedelta(hours=24)
            date = date_test
            y_train, y_tests = y_ser.loc[d:date_test], y_ser.loc[date_test:date_end]
            X_train, X_tests = X_df.loc[d:date_test, :], X_df.loc[date_test:date_end, :]
            out_dict['train'][date] = {'y': y_train.values, 'X': X_train.values, 'ts': X_train.index}
            out_dict['tests'][date] = {'y': y_tests.values, 'X': X_tests.values, 'ts': X_tests.index}
            out_dict['keys'].append(date)
        return out_dict

    def scale_data(self, data_dict):
        if not self.scale_bool:
            return data_dict
        scaled_dict = {'keys': [], 'train': {}, 'tests': {}}
        for d in data_dict['keys']:
            X_train = data_dict['train'][d]['X']
            X_tests = data_dict['tests'][d]['X']
            y_train = data_dict['train'][d]['y']
            y_tests = data_dict['tests'][d]['y']
            ts_train = data_dict['train'][d]['ts']
            ts_tests = data_dict['tests'][d]['ts']

            X_train_s, X_tests_s = self.scale_data_reg(X_train, X_tests, d)

            scaled_dict['train'][d] = {'y': y_train, 'X': X_train_s, 'ts': ts_train}
            scaled_dict['tests'][d] = {'y': y_tests, 'X': X_tests_s, 'ts': ts_tests}
            scaled_dict['keys'].append(d)
        return scaled_dict

    def scale_data_reg(self, X_train, X_tests, d):
        scaler_x = StandardScaler()
        X_train_s = scaler_x.fit_transform(X_train)
        X_tests_s = scaler_x.transform(X_tests)
        self.__scale_params_dict[d] = scaler_x
        return X_train_s, X_tests_s


### LOAD DATA ###
dump_path = 'C:/data/lle/model_data_dey1_03_06.pkl'
with open(dump_path, 'rb') as f:
    loaded_data = pickle.load(f)

df_data = loaded_data['df_data']

start_time = time(10, 0, 0)
end_time = time(17, 0, 0)

### Data Class
scale_bool = False
data_class = DataClass(scale_bool=scale_bool)

# Prepare data for modeling
y_col = 'class_150_10'
x_cols = [x for x in df_data.columns if not (x == 'class' or x.startswith('class_'))
          and x not in ['b_price', 'a_price']]


df_data = df_data[df_data['trd_gap'].abs() > 0]
df_data = df_data.between_time(start_time, end_time).dropna()

## Split data into train and test sets
n_train = 12
n_tests = 1
n_tot = n_train + n_tests

threshold = .45  # e.g., keep features explaining 90% of variance

sample_dates = pd.unique(df_data.index.date)
date_range_dict = {sample_dates[i]: list(sample_dates[i:i + n_tot])
                   for i in range(len(sample_dates) - n_tot + 1)}

split_dict = data_class.split_data(df_data, date_range_dict, n_tests, y_col=y_col, x_cols=x_cols)
scaled_dict = data_class.scale_data(split_dict)
# ### Modeling part ###
# for d in scaled_dict['keys']:
#     X_train = scaled_dict['train'][d]['X']
#     y_train = scaled_dict['train'][d]['y']
#     X_tests = scaled_dict['tests'][d]['X']
#     y_tests = scaled_dict['tests'][d]['y']


#     # Model fit: Random Forest
#     model = RandomForestClassifier(n_estimators=150, random_state=42, criterion='entropy')
#     model.fit(X_train, y_train)

#     # Feature selection based on importances
#     importances = model.feature_importances_
#     sorted_idx = np.argsort(importances)[::-1]
#     sorted_importances = importances[sorted_idx]
#     cumsum = np.cumsum(sorted_importances)
    
#     n_keep = np.searchsorted(cumsum, threshold) + 1
#     selected_idx = sorted_idx[:n_keep]
#     X_train_sel = X_train[:, selected_idx]
#     X_tests_sel = X_tests[:, selected_idx]

#     # Retrain model on selected features
#     model_sel = RandomForestClassifier(n_estimators=50, random_state=42, criterion='entropy')
#     model_sel.fit(X_train_sel, y_train)
#     predictions = model_sel.predict(X_tests_sel)

#     # Evaluate predictions against y_tests
#     accuracy = np.mean(predictions == y_tests)
#     print(f"Date: {d}, Test Accuracy: {accuracy:.3f}, Features used: {len(selected_idx)} (threshold={threshold})")

gap_mrg = 0.05
score_list = []
y_pred_all, y_tests_all = np.array(()), np.array(())
for d in scaled_dict['keys']:
    X_train = scaled_dict['train'][d]['X']
    y_train = scaled_dict['train'][d]['y']
    X_tests = scaled_dict['tests'][d]['X']
    y_tests = scaled_dict['tests'][d]['y']


    # Model fit: Random Forest
    model = RandomForestClassifier(n_estimators=150, random_state=42, criterion='entropy')
    model_class = ModelClass(model, thres_list=[0.30, 0.5], gap_mrg=gap_mrg, gap_bool=False)
    model_class.fit(X_train, y_train)
    
    # Feature selection based on importances
    selected_idx = model_class.feature_importances(threshold=threshold)

    # Retrain model on selected features
    # from sklearn.linear_model import LogisticRegression
    # model = LogisticRegression(max_iter=1000, random_state=42)
    # model_class.change_model(model)
    model_class.fit(X_train, y_train)
    y_pred = model_class.predict(X_tests)
    y_pred_train = model_class.predict(X_train)
    
    # Evaluate predictions against y_tests
    score = model_class.score(y_pred, y_tests)
    score_list.append(score)
    score_train = model_class.score(y_pred_train, y_train)
    bull, bear = (np.sum(y_pred == i) for i in [-1, 1])
    conf_mat_aux = confusion_matrix(y_tests, y_pred, labels=[-1, 0, 1])
    if len(y_pred_all) == 0:
        y_pred_all = y_pred
        y_tests_all = y_tests
    else:
        y_pred_all = np.concatenate((y_pred_all, y_pred))
        y_tests_all = np.concatenate((y_tests_all, y_tests))
    print(f"Date: {d}, Test Accuracy: {score:.3f} // {score_train:.3f}, Features used: {len(selected_idx)} (t={threshold}) ({bull}/{bear})")

conf_mat = confusion_matrix(y_tests_all, y_pred_all, labels=[-1, 0, 1])

### Martin data ###
"""
gap_mrg_list = [0.03, 0.04, 0.05, 0.07]
threshold_list = [.35, .45, .55]
n_train_list = [10, 12, 15]

out_dict = {n_train: {gap_mrg: {threshold: pd.DataFrame([]) for threshold in threshold_list}
            for gap_mrg in gap_mrg_list} for n_train in n_train_list}
for n_train in n_train_list:
    n_tot = n_train + n_tests

    date_range_dict = {sample_dates[i]: list(sample_dates[i:i + n_tot])
                   for i in range(len(sample_dates) - n_tot + 1)}

    split_dict = data_class.split_data(df_data, date_range_dict, n_tests, y_col=y_col, x_cols=x_cols)
    scaled_dict = data_class.scale_data(split_dict)
    for gap_mrg in gap_mrg_list:
        for threshold in threshold_list:
            score_list = []
            y_pred_all, y_tests_all = np.array(()), np.array(())
            for d in scaled_dict['keys']:
                X_train = scaled_dict['train'][d]['X']
                y_train = scaled_dict['train'][d]['y']
                X_tests = scaled_dict['tests'][d]['X']
                y_tests = scaled_dict['tests'][d]['y']

                # Model fit: Random Forest
                model = RandomForestClassifier(n_estimators=150, random_state=42, criterion='entropy')
                model_class = ModelClass(model, thres_list=[0.30, 0.5], gap_mrg=gap_mrg, gap_bool=False)
                model_class.fit(X_train, y_train)

                # Feature selection based on importances
                selected_idx = model_class.feature_importances(threshold=threshold)

                # Retrain model on selected features
                model_class.fit(X_train, y_train)

                # y_pred = model_class.predict_proba(X_tests)
                y_pred = model_class.predict(X_tests)
                df_pred = pd.DataFrame(y_pred, index=scaled_dict['tests'][d]['ts'])
                if out_dict[n_train][gap_mrg][threshold].empty:
                    out_dict[n_train][gap_mrg][threshold] = df_pred
                else:
                    out_dict[n_train][gap_mrg][threshold] = pd.concat((out_dict[n_train][gap_mrg][threshold], df_pred))

dump_path = 'C:/data/lle/model_output_dey1_10_150_20250301_20250623.pkl'
# dump_path = 'C:/data/lle/model_output_proba_dey1_10_150_20250301_20250623.pkl'

with open(dump_path, 'wb') as f:
    pickle.dump({
        'out_dict': out_dict
    }, f)
"""