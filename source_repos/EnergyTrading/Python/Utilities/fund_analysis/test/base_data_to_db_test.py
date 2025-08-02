import sys
import os

# Get the absolute path of the "fund_analysis" package in your current branch
package_path = os.path.abspath(r'C:\Users\krajcovic\Documents\GitHub\EnergyTrading\Python\Utilities\fund_analysis')

# Add it to sys.path
sys.path.insert(0, package_path)

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
params_dict['eD'] = dt.datetime(2025,5,9)
params_dict['ns'] = 2
params_dict['cont'] = False


fcst_range = pd.date_range(start=pd.to_datetime('2025-05-09'),
                            end=pd.to_datetime('2025-05-09'))
fcst_date = dt.datetime(2025,5,9)
inst = ModelDataAssembly(params_dict, fcst_date)

inst.fill_da_data_to_db(normalized=True)
inst.fill_da_data_to_db(normalized=False)
# inst.load_da_data(fcst_date)