from fund_analysis.models.models import Model
from fund_analysis.utils.model_data_assembly import ModelDataAssembly
import pandas as pd
import datetime as dt
import os
import pickle



load_or_dump = 'load'

# Get the current working directory
current_dir = os.getcwd()

# Build the path to the 'data/test' folder
data_test_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\fund_analysis\test\data'

file_path_processed = os.path.join(data_test_dir, 'processed_data.pkl')
with open(file_path_processed, 'rb') as f:
        processed_data = pickle.load(f)
        X_train, X_test, y_train, y_test = processed_data
        
inst = ModelDataAssembly({}, dt.datetime(2024,7,8))

X_train_scaled, X_test_scaled = inst.scale_data(X_train, X_test)

model_params_dict = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
            'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
            'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
            'n_estimators': 167, 'subsample': 0.2106044847212501,
            'nthread': -1}

model_inst = Model(X_train_scaled,
                    X_test_scaled,
                    y_train,
                    model_params_dict)

curve_pred = model_inst.model_predict_curve()