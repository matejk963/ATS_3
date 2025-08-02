import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

import warnings
import os
import sys
import pandas as pd
import numpy as np
import datetime as dt
from datetime import timedelta
from fund_analysis.fair_value_manager import FairValueManager
from fund_analysis.utils.model_data_assembly import ModelDataAssembly
from sklearn.preprocessing import PowerTransformer
from sklearn.metrics import mean_squared_error
from hyperopt import hp, tpe, fmin, Trials, STATUS_OK
import xgboost as xgb
import pickle

# Limit CPU usage globally
os.environ["OMP_NUM_THREADS"] = "8"  # Limit OpenMP to 4 threads
os.environ["MKL_NUM_THREADS"] = "8"  # Limit MKL to 4 threads
os.environ["NUMEXPR_NUM_THREADS"] = "8"  # Limit NumExpr to 4 threads
os.environ["OPENBLAS_NUM_THREADS"] = "8"  # Limit OpenBLAS to 4 threads

# Generate the combinations
base_products = ['M_1']
market_list = ['de', 'fr', 'be', 'nl', 'at', 'hu', 'cz', 'sk']
# market_list = ['es']
delivery_dict = ['base', 'peak']

products, markets, delivery = [], [], []

for product in base_products:
    for market in market_list:
        for delivery_option in delivery_dict:
            products.append(product)
            markets.append(market)
            delivery.append(delivery_option)

params_dict = {
    'product_list': products,
    'market_list': markets,
    'delivery_list': delivery,
    'year_list': [None] * len(market_list),
    'sD': dt.datetime(2020, 1, 1),
    'eD': dt.datetime(2025, 5, 31),
    'ns': 2,
    'cont': False
}

fcst_range = pd.date_range(start=pd.to_datetime('2025-05-30'),
                           end=pd.to_datetime('2025-05-30'),
                           freq='B')

inst = FairValueManager(params_dict=params_dict,
                        fcst_range=fcst_range)
mda_inst = ModelDataAssembly(params_dict=params_dict,
                             fcst_date=fcst_range[0])

base_data, base_data_nomralized = inst.call_for_base_data(fcst_range[0])

train_data, test_data, y_train, y_test = mda_inst.prepare_data(base_data)

best_parameters = {}

for market in market_list:
    print(f"Calibrating hyperparameters for {market}")
    
    df_inputs = train_data['base'].dropna()
    df_target = y_train[market].dropna()
    
    df_inputs = df_inputs.loc[df_inputs.index.date != dt.date(2025, 5, 30)]
    df_target = df_target.loc[df_target.index.date != dt.date(2025, 5, 30)]
    
    df_inputs, df_target = df_inputs.align(df_target, join='inner', axis=0)
    
    unique_dates = np.unique(df_inputs.index.date)
    
    def objective(params):
        params['max_depth'] = int(params['max_depth'])
        params['n_estimators'] = int(params['n_estimators'])
        
        xgb_model = xgb.XGBRegressor(n_jobs=4,  # Limit XGBoost threads
                                     **params)
        
        results = []
        true_values = []
        
        for i in range(-365, 0, 10):
            fcst_date = unique_dates[i]
            train_end = pd.to_datetime(fcst_date) - timedelta(hours=1)
            test_end = pd.to_datetime(fcst_date) + timedelta(days=10, hours=-1)
            
            X_train = df_inputs[:train_end].values
            y_train_values = df_target[:train_end].values.flatten()
            X_test = df_inputs[fcst_date:test_end].values
            y_test_values = df_target[fcst_date:test_end].values.flatten()
            
            scaler = PowerTransformer()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            xgb_model.fit(X_train_scaled, y_train_values)
            
            raw_prediction = xgb_model.predict(X_test_scaled)
            results.append(raw_prediction)
            true_values.append(y_test_values)
        
        y_pred = np.concatenate(results)
        y_true = np.concatenate(true_values)
        
        return {'loss': mean_squared_error(y_true, y_pred), 'status': STATUS_OK}
    
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
    
    trials = Trials()
    best = fmin(fn=objective,
                space=space,
                algo=tpe.suggest,
                max_evals=100,
                trials=trials)
    
    print(f"Best hyperparameters for {market}:", best)
    best_parameters[market] = best

file_path = r'//192.168.10.91/data/Data/Spot/Model/Inputs/model_parameters.pkl'

# Check if the file exists
if os.path.exists(file_path):
    # Load existing parameters
    with open(file_path, 'rb') as f:
        try:
            existing_parameters = pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            existing_parameters = {}  # Fallback if the file is corrupted or empty
    
    # Update existing parameters with new best parameters
    if isinstance(existing_parameters, dict) and isinstance(best_parameters, dict):
        existing_parameters.update(best_parameters)
    else:
        existing_parameters = best_parameters  # Ensure it's valid if it's not a dict

else:
    # If file does not exist, use best_parameters as is
    existing_parameters = best_parameters

# Save updated parameters
with open(file_path, 'wb') as f:
    pickle.dump(existing_parameters, f)
