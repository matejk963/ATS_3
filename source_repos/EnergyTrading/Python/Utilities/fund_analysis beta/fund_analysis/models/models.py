"""
Parent class for models used for predicting price direction
Classes receive dicts of scenarios and perform training
    and parallel forecast
"""

import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import xgboost as xgb
from joblib import Parallel, delayed
import pickle
try:
    import pynvml
except:
    pass
import time
pynvml.nvmlInit()
import sys

class Model:
    fitted_model = {}
    fcst_curve_dict = {}
    
    def __init__(self, X_train_scaled: pd.DataFrame,
                    X_test_scaled: dict,
                    y_train: pd.DataFrame,
                    model_params_dict: dict):
        self._x_train = X_train_scaled
        self._x_test = X_test_scaled
        self._y_train = y_train
        self._model_params_dict = model_params_dict
        self.fitted_model = {}
        self.fcst_curve_dict = {}
    @property
    def x_train(self):
        return self._x_train
    
    @property
    def x_test(self):
        return self._x_test
    
    @property
    def y_train(self):
        return self._y_train
    
    @property
    def model_params_dict(self):
        return self._model_params_dict
    
    def init_model(self):
        pass
    
    
    # Parameters are taken based on market
    def model_fit(self):
        file_path = r'//192.168.10.91/d/data/Data/Spot/Model/Inputs/model_parameters.pkl'
        with open(file_path, 'rb') as f:
            model_params_dict = pickle.load(f)
        for market, y_train in self.y_train.items():
            market_params_dict = model_params_dict[market] if market in model_params_dict else model_params_dict['de']
            market_params_dict = {
                                    k: int(v) if isinstance(v, float) and v.is_integer() else v
                                    for k, v in market_params_dict.items()
                                }
            market_params_dict['nthread'] = -1
            market_params_dict['tree_method'] = 'hist'   # Use histogram method (required with new device parameter)
            market_params_dict['device'] ='cuda'
            x_train = self.x_train.dropna().copy()
            y_train_temp = y_train.dropna().copy()
            x_train_aligned, y_train_aligned = x_train.align(y_train_temp,
                                                            join='inner',
                                                            axis=0)
            y_train_aligned['ghr'] = pd.to_numeric(y_train_aligned['ghr'], errors='coerce')
            self.fitted_model[market] = XGBRegressor(**market_params_dict).fit(x_train_aligned.values,
                                                                        y_train_aligned)
    
    # def model_fit(self):
    #     for market, y_train in self.y_train.items():
    #         x_train = self.x_train.dropna().copy()
    #         y_train_temp = y_train.dropna().copy()
    #         x_train_aligned, y_train_aligned = x_train.align(y_train_temp,
    #                                                         join='inner',
    #                                                         axis=0)
    #         y_train_aligned['ghr'] = pd.to_numeric(y_train_aligned['ghr'], errors='coerce')
    #         self.fitted_model[market] = XGBRegressor(**self.model_params_dict).fit(x_train_aligned.values,
    #                                                                     y_train_aligned)
        
    # def model_predict_curve(self):
    #     # Fit model if not fitted
    #     if not self.fitted_model:
    #         self.model_fit()
    #     # Adjust for y_train prediction residuals
    #     # Include after testing the pure model prediction
        
    #     # Pralelize prediction
    #     # Method used for prarelization
    #     def process_forecast(market: str,
    #                         scen_name: str,
    #                         x_test_scen: pd.DataFrame):
    #         return pd.Series(self.fitted_model[market].predict(x_test_scen.values),
    #                             name=scen_name,
    #                             index=x_test_scen.index)
    #     # Prarell run
    #     for market in self.fitted_model.keys():
    #         market_results = Parallel(n_jobs=8, backend='threading')(
    #                             delayed(process_forecast)(market, scen_name, x_test_scen.dropna())
    #                             for scen_name, x_test_scen in self.x_test.items()
    #                         )
    #         self.fcst_curve_dict[market] = pd.concat(market_results, axis=1)
    #     # Return concated results
    #     return self.fcst_curve_dict
    
    
    # def model_predict_curve(self):
    #     # Fit model if not fitted
    #     if not self.fitted_model:
    #         self.model_fit()

    #     # GPU-accelerated prediction function for multiple scenarios at once
    #     for market in self.fitted_model.keys():
    #         # Get the Booster from the fitted XGBRegressor model
    #         booster_model = self.fitted_model[market].get_booster()

    #         # Concatenate all scenario data into a single DataFrame
    #         scenario_data = []
    #         scenario_names = []
    #         scenario_indices = []
    #         for scen_name, x_test_scen in self.x_test.items():
    #             scenario_data.append(x_test_scen.dropna().values)
    #             scenario_names.append(scen_name)
    #             scenario_indices.append(x_test_scen.dropna().index)

    #         # Stack scenario data to predict at once
    #         scenario_data_stacked = np.vstack(scenario_data)
    #         dmatrix = xgb.DMatrix(scenario_data_stacked)

    #         # Set GPU predictor for XGBoost Booster model
    #         # booster_model.set_param({'predictor': 'gpu_predictor'})

    #         # Perform prediction using GPU (use stacked scenario data)
    #         predictions = booster_model.predict(dmatrix)

    #         # Split predictions back into individual scenarios
    #         split_indices = np.cumsum([len(index) for index in scenario_indices[:-1]])
    #         scenario_predictions = np.split(predictions, split_indices)

    #         market_results = []
    #         for scen_name, scen_pred, scen_index in zip(scenario_names, scenario_predictions, scenario_indices):
    #             market_results.append(pd.Series(scen_pred, name=scen_name, index=scen_index))

    #         # Combine all scenarios into a single DataFrame for each market
    #         self.fcst_curve_dict[market] = pd.concat(market_results, axis=1)

    #     # Return concatenated results
    #     return self.fcst_curve_dict
    

    


    def model_predict_curve(self):
        # Fit model if not fitted
        if not self.fitted_model:
            self.model_fit()
            
        pynvml.nvmlInit()
    
        # GPU-accelerated prediction function for multiple scenarios at once
        for market in self.fitted_model.keys():
            # Get the Booster from the fitted XGBRegressor model
            booster_model = self.fitted_model[market].get_booster()
    
            # Concatenate all scenario data into a single DataFrame
            scenario_data = []
            scenario_names = []
            scenario_indices = []
            for scen_name, x_test_scen in self.x_test.items():
                scenario_data.append(x_test_scen.dropna().values)
                scenario_names.append(scen_name)
                scenario_indices.append(x_test_scen.dropna().index)
    
            # Stack scenario data to predict at once
            scenario_data_stacked = np.vstack(scenario_data)
            dmatrix = xgb.DMatrix(scenario_data_stacked)
    
            # Set GPU predictor for XGBoost Booster model
            # booster_model.set_param({'predictor': 'gpu_predictor'})
    
            # Perform prediction using GPU (use stacked scenario data)
            predictions = booster_model.predict(dmatrix)
    
            # Split predictions back into individual scenarios
            split_indices = np.cumsum([len(index) for index in scenario_indices[:-1]])
            scenario_predictions = np.split(predictions, split_indices)
    
            market_results = []
            for scen_name, scen_pred, scen_index in zip(scenario_names, scenario_predictions, scenario_indices):
                market_results.append(pd.Series(scen_pred, name=scen_name, index=scen_index))
    
            # Combine all scenarios into a single DataFrame for each market
            self.fcst_curve_dict[market] = pd.concat(market_results, axis=1)
    
            # Monitor GPU temperature
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            print(f"GPU Temperature: {temperature}°C")
            if temperature > 80:
                print("Warning: GPU temperature is too high. Pausing execution for cooling.")
                while temperature > 70:
                    time.sleep(5)  # Wait for 10 seconds before rechecking the temperature
                    temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    print(f"GPU Temperature: {temperature}°C")
                print("Temperature is back to a safe level. Resuming execution.")
    
            time.sleep(1)  # Sleep to avoid excessive temperature monitoring frequency
    
        # Return concatenated results
        return self.fcst_curve_dict
    
    pynvml.nvmlShutdown()

    