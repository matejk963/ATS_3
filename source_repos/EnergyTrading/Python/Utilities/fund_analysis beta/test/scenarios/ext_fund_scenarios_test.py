from fund_analysis.scenarios.external_fund_scenarios import ExternalFundScenarios
import pandas as pd
import datetime as dt
import pickle
import os

base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['W_1', 'W_2', 'M_1', 'M_2', 'M_3']
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
params_dict['eD'] = dt.datetime(2024,11,20)
params_dict['ns'] = 2
params_dict['cont'] = False

data_test_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\fund_analysis\test\data'

file_path = r'W:\Data\Spot\Model\temp\base_data_20241120.pkl'
with open(file_path, 'rb') as f:
    base_data = pickle.load(f)
file_path = r'W:\Data\Spot\Model\temp\base_data_normalized_20241120.pkl'
with open(file_path, 'rb') as f:
    base_data_normalized = pickle.load(f)

inst = ExternalFundScenarios(base_data,
                            base_data_normalized,
                            params_dict)
scen_list = [a/100 for a in list(range(10,99, 10))]
scen_dict, percentiles_dict, norm_curve, res_normal_curve, monthly_dist = inst.get_historical_scenarios(scen_list=scen_list)