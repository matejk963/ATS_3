from fund_analysis.utils.model_data_assembly import ModelDataAssembly
import pandas as pd
import datetime as dt
import os
import pickle

base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3', 'Y_1', 'Y_2', 'Y_3']
market_list = ['de', 'fr']
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
params_dict['eD'] = dt.datetime(2024,11,5)
params_dict['ns'] = 2
params_dict['cont'] = False


fcst_range = pd.date_range(start=pd.to_datetime('2024-11-05'),
                            end=pd.to_datetime('2024-11-05'))
fcst_date = dt.datetime(2024,11,5)
inst = ModelDataAssembly(params_dict, fcst_date)
base_data = inst.create_base_data()
# Get the current working directory
current_dir = os.path.dirname(__file__)

# Build the path to the 'data/test' folder
data_test_dir = os.path.join(current_dir, 'data')

# Example of using the path for a file

load_or_dump = 'dump'

# Example of using the path for a file
file_path = os.path.join(data_test_dir, 'base_data.pkl')

if load_or_dump in ['dump']:    
    base_data = inst.create_base_data()
    base_data_normalized = inst.create_base_data(normalized=True)
    file_path = os.path.join(data_test_dir, f'base_data_{fcst_date.strftime('%Y-%m-%d')}.pkl')
    with open(file_path, 'wb') as f:
        pickle.dump(base_data, f)
    file_path = os.path.join(data_test_dir, f'data_dict_normalized_{fcst_date.strftime('%Y-%m-%d')}.pkl')
    with open(file_path, 'wb') as f:
        pickle.dump(base_data_normalized, f)
    file_path = os.path.join(data_test_dir, 'av_cap_cols.pkl')
    with open(file_path, 'wb') as f:
            pickle.dump(inst.av_cap_cols,f)
elif load_or_dump in ['load']:
    file_path = os.path.join(data_test_dir, 'av_cap_cols.pkl')
    with open(file_path, 'rb') as f:
        inst.av_cap_cols = pickle.load(f)
    file_path = os.path.join(data_test_dir, f'base_data_{fcst_date.strftime('%Y-%m-%d')}.pkl')
    with open(file_path, 'rb') as f:
        base_data = pickle.load(f)


X_train, X_test, y_train, y_test = inst.prepare_data(base_data)
prepared_data = [X_train, X_test, y_train, y_test]

file_path = os.path.join(data_test_dir, f'prepared_data_{fcst_date.strftime('%Y-%m-%d')}.pkl')
