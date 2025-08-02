# -*- coding: utf-8 -*-
"""
Created on Tue Oct  3 18:23:12 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import joblib


from Spot.ExTreesSpotClass import ModelTuning

# nn_o.load_data(folder_path='s:/Algo/Database/Model Data',
#                input_files=['wa_rld_arr.txt', 'wa_prices_arr.txt',
#                             'gas_arr.txt', 'coal_arr.txt', 
#                             'eua_arr.txt'],
#                y_file = 'long_arr.txt',
#                normalize=[1,0,0,0,0])


hyperparameters = {
    'n_estimators': [a for a in range(20,80,5)],
    'max_features': ['log2', 'sqrt'],
    'max_depth': [a for a in range(5,55,5)],
    'min_samples_split': [5,10,15,20],
    'min_samples_leaf': [a for a in range(30,50,2)]
}

input_files = ['wa_rld_arr.txt',
               'da_rld_arr.txt']
# input_files = ['wa_moments_arr.txt',
#                 'da_moments_arr.txt',
#                 'av_cap_fct_moments_arr.txt',
#                 'av_cap_hist_moments_arr.txt']
input_files = ['wa_rld_to_norm_arr.txt',
                'mcr_arr.txt',
                'gas_to_rld_av_cap_arr.txt',
                # 'coal_to_rld_av_cap_arr.txt',
                'av_gas_wa_fct_df_arr.txt']
                # 'av_coal_wa_fct_df_arr.txt']
# input_files = ['wa_rld_to_norm_arr.txt',
#                'da_moments_arr.txt']

model_tuner = ModelTuning()
model_tuner.load_data(folder_path='s:/Algo/Database/Model Data',
               input_files=input_files,
               y_file = 'long_arr.txt',
               normalize=[0,0,0,1])

# model_tuner.load_data(folder_path='s:/Algo/Database/Model Data',
#                input_files=['wa_rld_arr.txt',
#                             'da_rld_arr.txt',
#                             'wa_ghr_arr.txt',
#                             'ma_ghr_arr.txt'],
#                y_file = 'long_arr.txt',
#                normalize=[1,1,0,0])

best_hyperparameters = model_tuner.tune_model(hyperparameters)

# accuracy = model_tuner.evaluate_model(best_hyperparameters)
roc_auc = model_tuner.evaluate_model(best_hyperparameters)
model_tuner.save_best_model()

print(f"Best Hyperparameters for each input: {best_hyperparameters}")
# print(f"Validation accuracy with best hyperparameters: {accuracy}")
print(f"Validation roc_auc with best hyperparameters: {roc_auc}")

data_dict = model_tuner.get_loaded_data()

x_train = data_dict['x_train']
x_test = data_dict['x_test']
y_train = data_dict['y_train']
y_test = data_dict['y_test']

predictions = model_tuner.predict(x_test)
probabilities = model_tuner.predict_proba(x_test)

wa_prices = np.loadtxt('s:/Algo/Database/Model Data/wa_prices_arr.txt', delimiter=',')
spot = np.loadtxt('s:/Algo/Database/Model Data/wa_spot_arr.txt', delimiter=',')


pred_idx = len(predictions)
pnl_arr = np.where(predictions.reshape(-1,1) == 0,
                   wa_prices[-pred_idx:].reshape(-1,1)-spot[-pred_idx:].reshape(-1,1),
                   spot[-pred_idx:].reshape(-1,1)-wa_prices[-pred_idx:].reshape(-1,1))

print(input_files)
plt.plot(pnl_arr.cumsum())

model_tuner.plot_feature_importance()