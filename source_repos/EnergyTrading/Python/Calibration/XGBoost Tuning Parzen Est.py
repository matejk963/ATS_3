# -*- coding: utf-8 -*-
"""
Created on Fri May 17 09:59:01 2024

@author: krajcovic
"""

import warnings
warnings.filterwarnings('ignore')




import sys
sys.path.append(r'X:')



import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from datetime import datetime, timedelta
from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import FuturesMonitor as FM
from Spot.SpotModelClass import PowerModel as PM

from sklearn.ensemble import ExtraTreesRegressor
from sklearn.preprocessing import StandardScaler, PowerTransformer
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor
import xgboost as xgb

from hyperopt import hp, tpe, fmin, Trials, STATUS_OK

from sklearn.metrics import accuracy_score, mean_squared_error

# Create dictionary for parameters
params_dict = {}
params_dict['market_list'] = ['hu', 'cz']
params_dict['product_list'] = ['M.7']
params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2022,6,22)
params_dict['eD'] = dt.datetime(2024,4,26)
params_dict['ns'] = 2
params_dict['cont'] = False

pm_inst = PM(params_dict)

da_data = pm_inst.assemble_da_data()

da_data = da_data.dropna().copy()

spot_df = da_data.copy()

# spot_df['ghr'] = spot_df['de']/(spot_df['ttf_da']+spot_df['eua']*0.2)
#spot_df['chr'] = spot_df['de']/(spot_df['spot_coal']/6.5+spot_df['eua']*0.35)
spot_df['mcr'] = (spot_df['ttf_da']+spot_df['eua']*0.2)/(spot_df['spot_coal']/6.5+spot_df['eua']*0.35)
# spot_df = spot_df.rename(columns={'hu': 'hu_spot'})
# spot_df['spread'] = spot_df['hu_ghr']-spot_df['cz_ghr']

df = spot_df.copy()

unique_dates = np.unique(df.index.date)

df_inputs = df.drop(['hu', 'hu_ghr','cz', 'cz_ghr',  'spread'], axis=1).copy()
df_target1 = df[['cz_ghr']].copy()
df_target2 = df[['hu_ghr']].copy()


def objective(params):
    # Cast hyperparameters to appropriate types
    params['max_depth'] = int(params['max_depth'])
    params['n_estimators'] = int(params['n_estimators'])
    
    # Initialize the model with the given hyperparameters
    xgb_model = xgb.XGBRegressor(**params)
    
    results1 = []
    results2 = []
    true_values1 = []
    true_values2 = []

    # Loop through unique_dates in steps of 10 days
    for i in range(-365, 0, 10):
        fcst_date = unique_dates[i]
        train_end = pd.to_datetime(fcst_date) - timedelta(hours=1)
        test_end = pd.to_datetime(fcst_date) + timedelta(days=10, hours=-1)  # Forecast next 10 days
    
        # Split data into training and test sets
        X_train = df_inputs[:train_end].values
        y_train1, y_train2 = df_target1[:train_end].values.flatten(), df_target2[:train_end].values.flatten()
        X_test = df_inputs[fcst_date:test_end].values
        y_test1, y_test2 = df_target1[fcst_date:test_end].values.flatten(), df_target2[fcst_date:test_end].values.flatten()
    
        # Scale the data
        scaler = PowerTransformer()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
    
        # # Train the model
        # xgb_model.fit(X_train_scaled, y_train1)
    
        # # Make predictions
        # raw_prediction1 = xgb_model.predict(X_test_scaled)
        # results1.append(raw_prediction1)
        # true_values1.append(y_test1)
        
        # Train the model
        xgb_model.fit(X_train_scaled, y_train2)
    
        # Make predictions
        raw_prediction2 = xgb_model.predict(X_test_scaled)
        results2.append(raw_prediction2)
        true_values2.append(y_test2)

    # Concatenate results and true values
    # y_pred1 = np.concatenate(results1)
    # y_true1 = np.concatenate(true_values1)
    y_pred2 = np.concatenate(results2)
    y_true2 = np.concatenate(true_values2)
    # y_pred = y_pred1 - y_pred2
    # y_true = y_true1 - y_true2
    
    # Calculate mean squared error
    score = mean_squared_error(y_true2, y_pred2)
    return {'loss': score, 'status': STATUS_OK}


# Define the search space
space = {
    'n_estimators': hp.quniform('n_estimators', 30, 200, 1),
    'max_depth': hp.quniform('max_depth', 2, 32, 1),
    'learning_rate': hp.loguniform('learning_rate', -5, -1),
    'subsample': hp.uniform('subsample', 0.1, 1),
    'colsample_bytree': hp.uniform('colsample_bytree', 0.1, 1),
    'min_child_weight': hp.quniform('min_child_weight', 1, 20, 1),
    'gamma': hp.loguniform('gamma', -5, 0),
    'lambda': hp.loguniform('lambda', -5, 0),
    'alpha': hp.loguniform('alpha', -5, 0)
}

# Run the optimization
trials = Trials()
best = fmin(fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=100,
            trials=trials)

print("Best hyperparameters:", best)

