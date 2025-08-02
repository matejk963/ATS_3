import sys
import os

# Remove original fund_analysis path if present
original_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')
if original_path in sys.path:
    sys.path.remove(original_path)

# Add beta fund_analysis parent path (so 'fund_analysis' is importable)
beta_parent_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis beta')
if beta_parent_path not in sys.path:
    sys.path.insert(0, beta_parent_path)

from fund_analysis.fair_value_manager import FairValueManager
import pandas as pd
import datetime as dt
import os
import pickle


base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['D_1', 'D_2', 'D_3', 'D_4', 'D_5', 'D_6', 'D_7', 'D_8',
                 'Wknd_0', 'Wknd_1', 'Wknd_2', 'Wknd_3',
                 'W_1', 'W_2', 'W_3', 'W_4',
                 'M_1', 'M_2', 'M_3', 'M_4', 'M_5', 'M_6',
                 'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7', 'Q_8',
                 'Y_1', 'Y_2', 'Y_3']
# base_products = ['M_1', 'M_2', 'M_3', 'M_4', 'M_5', 'M_6',
#                  'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7', 'Q_8',
#                  'Y_1', 'Y_2']
# base_products = ['D_1', 'D_2', 'D_3', 'D_4', 'D_5', 'D_6', 'D_7', 'D_8',
#                  'Wknd_0', 'Wknd_1', 'Wknd_2', 'Wknd_3',
#                  'W_1', 'W_2', 'W_3', 'W_4', 'M_1']
market_list = ['de', 'fr', 'be', 'nl', 'at', 'hu', 'cz', 'sk', 'ro']
market_list = ['de', 'fr', 'at', 'cz', 'nl', 'hu']
# market_list = ['hu']
delivery_dict = ['base', 'peak']

# Generate the combinations
products = []
markets = []
delivery = []

for product in base_products:
    for market in market_list:
        for delivery_option in delivery_dict:
            products.append(product)
            markets.append(market)
            delivery.append(delivery_option)

params_dict = {}

params_dict['product_list'] = products

params_dict['market_list'] = markets

params_dict['delivery_list'] = delivery 

params_dict['year_list'] = [None] * len(params_dict['market_list'])
params_dict['ns'] = 2
params_dict['cont'] = False


params_dict['sD'] = dt.datetime(2020,1,1)
params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
params_dict['eD'] = dt.datetime(2025,7,11)
params_dict['ns'] = 2
params_dict['cont'] = False

# model_params_dict = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
#             'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
#             'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
#             'n_estimators': 167, 'subsample': 0.2106044847212501,
#             'nthread': -1,
#             'tree_method':'hist',       # Use histogram method (required with new device parameter)
#             'device':'cuda'}

model_params_dict = {'alpha': 0.977484347812482, 'colsample_bytree': 0.6255926016338145,
                    'gamma': 0.34516275640918953, 'lambda': 0.5072451009910257,
                    'learning_rate': 0.046930733309289374, 'max_depth': 20,
                    'min_child_weight': 17, 'n_estimators': 164, 'subsample': 0.19263191007876687,
                    'nthread': -1,
                    'tree_method':'hist',       # Use histogram method (required with new device parameter)
                    'device':'cuda'}


fcst_range = pd.date_range(start=pd.to_datetime('2025-07-11'),
                            end=pd.to_datetime('2025-07-11'),
                            freq='B')
inst = FairValueManager(params_dict=params_dict,
                        fcst_range=fcst_range)

scen_list = []
master_params_dict = {}
master_params_dict['ResidualDemand'] = {'params': {
                                    'fund_type': 'ResidualDemand',
                                    'params_dict': params_dict},
                                'scen_type': {'historical' : scen_list}}
master_params_dict['AvailableCapacityData'] = {'params': {
                                    'params_dict': params_dict},
                                'scen_type': {'historical' : scen_list}}
# master_params_dict['mcr'] = {'params': {
#                                     'fuel_type': 'mcr'},
#                                 'scen_type': {'mcr': None}}

# file_path = r'C:\Users\krajcovic\Documents\temp\base_data_20250328.pkl'
# with open(file_path, 'rb') as f:
#     base_data = pickle.load(f)
# file_path = r'C:\Users\krajcovic\Documents\temp\base_data_norm_20250328.pkl'
# with open(file_path, 'rb') as f:
#     base_data_normalized = pickle.load(f)

    
inst.get_fcst_curves(model_params_dict=model_params_dict,
                    return_test_data=True,
                    master_params_dict=master_params_dict)
                    # base_data=base_data,
                    # base_data_normalized=base_data_normalized)
                    
# temp = curve_pred_nominal[list(curve_pred_nominal)[0]]['de'].copy()                                                                
# columns_dict = {
#     'base_col': ['base'],
#     'base_sim': [f'ExtDataSim_{int(a)}' for a in range(1, 101)],
#     'base_mcr': ['mcr_-1_std', 'mcr_1_std'],
#     'base_avcap': ['AvailableCapacityData_10th', 'AvailableCapacityData_mean', 'AvailableCapacityData_90th'],
#     'mcr_lower_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'mcr_-1_std' in a)],
#     'mcr_upper_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'mcr_1_std' in a)],
#     'avcap_lower_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_10th' in a)],
#     'avcap_mean_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_mean' in a)],
#     'avcap_upper_sim': [a for a in temp.columns if ('ExtDataSim' in a and 'AvailableCapacityData_90th' in a)],
# }
# del temp


# country_spreads = inst.calculate_country_spreads(curve_pred_nominal, base_products, columns_dict)
# period_spreads = inst.calculate_period_spreads(curve_pred_nominal, base_products, columns_dict)
# b_p_spreads = inst.calculate_base_peak_spreads(curve_pred_nominal, base_products, columns_dict)
# css_spreads = inst.calculate_clean_spark_spreads(curve_pred_nominal, base_products, columns_dict, fuel_data)
# capa_spreads = inst.calculate_capa_spreads(curve_pred_nominal, base_products, columns_dict)

# file_path = r'X:\Data\Spot\Model\Forecasts\curve_pred_'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(curve_pred, f)
    
# file_path = r'X:\Data\Spot\Model\Forecasts\curve_pred_nominal'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(curve_pred_nominal, f)



# def save_spreads_to_pickle(file_path, **spreads_dict):
#     """
#     Save calculated spreads to pickle files at a specified location.

#     Args:
#         file_path (str): The directory where pickle files will be saved.
#         spreads_dict (dict): Named spreads dictionaries to save (name=spread).
#     """
#     # Ensure the directory exists
#     if not os.path.exists(file_path):
#         os.makedirs(file_path)
    
#     # Save each spread to a pickle file
#     for spread_name, spread_data in spreads_dict.items():
#         save_path = os.path.join(file_path, f"{spread_name}.pkl")
#         with open(save_path, 'wb') as f:
#             pickle.dump(spread_data, f)
#         print(f"Saved: {spread_name} -> {save_path}")

# # Define the spreads and file path
# file_path = r'X:\Data\Spot\Model\Forecasts'

# save_spreads_to_pickle(
#     file_path,
#     country_spreads=country_spreads,
#     period_spreads=period_spreads,
#     b_p_spreads=b_p_spreads,
#     css_spreads=css_spreads,
#     capa_spreads=capa_spreads
# )

    
# first_fcst_date = list(curve_pred_nominal)[-1]
# rld_cols = [a for a in curve_pred_nominal[first_fcst_date]['de'] if 'base' not in a]
# mean_dict = {}
# for fcst_date, fcst_date_dict in curve_pred_nominal.items():
#     mean_dict[fcst_date] = {}
#     for market, market_df in fcst_date_dict.items():
#         mean_dict[fcst_date][market] = pd.DataFrame(market_df[rld_cols].mean(axis=1),columns=[market])
        
# file_path = r'X:\Data\Spot\Model\Forecasts\curve_pred_mean'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(mean_dict, f)
    
# base_dict = {}
# for fcst_date, fcst_date_dict in curve_pred_nominal.items():
#     base_dict[fcst_date] = {}
#     for market, market_df in fcst_date_dict.items():
#         base_dict[fcst_date][market] = pd.DataFrame(market_df[['base']]).rename(columns={'base': market})
        
# file_path = r'X:\Data\Spot\Model\Forecasts\curve_pred_base'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(base_dict, f)
    
# file_path = r'X:\Data\Spot\Model\Forecasts\test_data'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(test_data, f)
    
# file_path = r'X:\Data\Spot\Model\Forecasts\train_data'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(train_data, f)
    
# file_path = r'X:\Data\Spot\Model\Forecasts\y_data'
# file_path = f"{file_path}_{fcst_range[0].strftime('%Y-%m-%d')}.pkl"
# with open(file_path, 'wb') as f:
#     pickle.dump(y_train, f)