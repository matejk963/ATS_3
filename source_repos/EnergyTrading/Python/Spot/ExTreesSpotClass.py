# -*- coding: utf-8 -*-
"""
Created on Tue Oct  3 18:18:36 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import os

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, TimeSeriesSplit  # <-- Added RandomizedSearchCV
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import roc_auc_score, roc_curve
import logging
import joblib




class IntegratedExtraTrees:
    def __init__(self):
        self.model = None

    def fit(self, X, y):
        self.model.fit(X, y)

    def predict(self, X):
        return self.model.predict(X)

    def predict_proba(self, X):
        return self.model.predict_proba(X)[:, 1]  # probabilities for the positive class
    

class ModelTuning:
    
    def __init__(self, log_dir=None):
        self.x_train = []
        self.y_train = []
        self.x_test = []
        self.y_test = []
        self.feature_names = []  # Initialize feature names as an empty list
        if log_dir is None:
            log_dir = r's:\Algo\Models\Logs'  # Default directory (current directory)
        log_file_path = os.path.join(log_dir, "model_tuning_logs.log")
        print(log_file_path)
        logging.basicConfig(filename=log_file_path,
                            level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logger = logging.getLogger()
        fh = logging.FileHandler(log_file_path)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logging.info("ModelTuning instance created")

    def _try_load_file(self, file_path):
        data = np.loadtxt(file_path)
        mean = np.mean(data)
        std = np.std(data)
        return data, mean, std
    
    def load_data(self, folder_path, input_files, y_file, test_size=0.2, normalize=None):
        x_data_list = []
        for file_name in input_files:
            x_data, _, _ = self._try_load_file(f"{folder_path}/{file_name}")
            if len(x_data.shape) == 1:
                x_data = x_data.reshape(-1, 1)
            x_data_list.append(x_data)
        
        # Concatenate all data sources horizontally
        X_combined = np.hstack(x_data_list)

        # Assume each input file represents a single feature.
        # Therefore, using file names (without extensions) as feature names.
        self.feature_names = [os.path.splitext(f)[0] for f in input_files]

        y_data_full = self._try_load_file(f"{folder_path}/{y_file}")[0]
        y_data_full = y_data_full.reshape(-1)

        # Train-test split on combined data
        self.x_train, self.x_test, self.y_train, self.y_test = train_test_split(X_combined, y_data_full, test_size=test_size, shuffle=False)
        
        logging.info(f"Data loaded from {folder_path}")
        logging.info(f"Train data shape: {self.x_train.shape}")
        logging.info(f"Test data shape: {self.x_test.shape}")
        logging.info(f"Number of training labels: {len(self.y_train)}")
        logging.info(f"Number of testing labels: {len(self.y_test)}")
    
    def tune_model(self, hyperparameters):
        estimator = ExtraTreesClassifier()
        grid_search = GridSearchCV(estimator, hyperparameters, cv=3, scoring='roc_auc', n_jobs=-1)
        grid_search.fit(self.x_train, self.y_train)
        logging.info(f"Best parameters found: {grid_search.best_params_}")
        return grid_search.best_params_
    
    # def tune_model(self, hyperparameters, n_iter=500):
    #     estimator = ExtraTreesClassifier()

    #     # Time series cross-validation
    #     tscv = TimeSeriesSplit(n_splits=10)

    #     random_search = RandomizedSearchCV(estimator, hyperparameters, n_iter=n_iter, cv=tscv, scoring='roc_auc', n_jobs=-1)
    #     random_search.fit(self.x_train, self.y_train)
        
    #     logging.info(f"Best parameters found: {random_search.best_params_}")
    #     return random_search.best_params_
    
    def get_loaded_data(self):
        """Retrieve the loaded train and test data."""
        if self.x_train is None or len(self.x_train) == 0 or \
           self.x_test is None or len(self.x_test) == 0 or \
           self.y_train is None or len(self.y_train) == 0 or \
           self.y_test is None or len(self.y_test) == 0:
            logging.error("Data has not been loaded yet!")
            raise ValueError("Data has not been loaded yet!")
        
        return {
            'x_train': self.x_train,
            'x_test': self.x_test,
            'y_train': self.y_train,
            'y_test': self.y_test
        }

    def evaluate_model(self, best_params):
        model = IntegratedExtraTrees()
        model.model = ExtraTreesClassifier(**best_params)
        model.fit(self.x_train, self.y_train)

        probabilities = model.predict_proba(self.x_test)
        roc_auc = roc_auc_score(self.y_test, probabilities)
        logging.info(f"ROC AUC Score: {roc_auc}")

        self.trained_model = model  # Store the trained model

        return roc_auc

    def predict(self, X_new):
        if self.trained_model is None:
            logging.error("The model has not been trained yet!")
            raise ValueError("The model has not been trained yet!")
        return self.trained_model.predict(X_new)

    def predict_proba(self, X_new):
        if self.trained_model is None:
            logging.error("The model has not been trained yet!")
            raise ValueError("The model has not been trained yet!")
        return self.trained_model.predict_proba(X_new)
    
    def save_best_model(self, save_dir=r'c:\Users\krajcovic\Documents\Algo\Projects\Project_ALGO\seved_models\ExTrees_models'):  # Default save directory is the current directory
        if hasattr(self, 'trained_model') and self.trained_model:
            current_time = dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            filename = os.path.join(save_dir, f'ExTrees_BestMod_{current_time}.joblib')
            joblib.dump(self.trained_model, filename)
            logging.info(f"Best model saved to {filename}")
        else:
            logging.error("No trained model found. Train the model first.")
            raise ValueError("No trained model found. Train the model first.")
            
    def plot_feature_importance(self):
        if not hasattr(self, 'trained_model') or self.trained_model is None:
            logging.error("The model has not been trained yet!")
            raise ValueError("The model has not been trained yet!")
    
        importances = self.trained_model.model.feature_importances_
    
        # Create a dataframe to display the features and their importance
        df_features = pd.DataFrame({
            'Feature Index': range(len(importances)),
            'Importance': importances
        })
    
        # Print the dataframe
        print(df_features)
    
        # Plot the feature importances
        plt.figure(figsize=(10, 6))
        plt.title("Feature importances")
        plt.bar(range(len(importances)), importances, align="center")
        plt.xticks(range(len(importances)), range(len(importances)), rotation=90)
        plt.xlim([-1, len(importances)])
        plt.show()
            
    # def plot_feature_importance(self):
    #     if not hasattr(self, 'trained_model') or self.trained_model is None:
    #         logging.error("The model has not been trained yet!")
    #         raise ValueError("The model has not been trained yet!")
        
    #     if not self.feature_names:
    #         logging.warning("Feature names are not available!")
        
    #     importances = self.trained_model.model.feature_importances_
        
    #     # Sort feature importances in descending order and get the indices
    #     indices = np.argsort(importances)[::-1]
        
    #     # Plot the feature importances
    #     plt.figure(figsize=(10, 6))
    #     plt.title("Feature importances")
    #     plt.bar(range(len(importances)), importances[indices], align="center")
        
    #     # Use feature names for label if available, otherwise use indices
    #     labels = self.feature_names if self.feature_names else indices
    #     plt.xticks(range(len(importances)), [labels[i] for i in indices], rotation=90)
        
    #     plt.xlim([-1, len(importances)])
    #     plt.show()