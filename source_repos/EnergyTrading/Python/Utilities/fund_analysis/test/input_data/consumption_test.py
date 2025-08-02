from fund_analysis.input_data.consumption import Consumption
import pandas as pd
import datetime as dt

base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['W_1', 'W_2', 'M_1', 'M_2']
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
params_dict['eD'] = dt.datetime(2025,4,17)
params_dict['ns'] = 2
params_dict['cont'] = False

ef_inst = Consumption(params_dict, normalize_bool=True)

# ef_inst.fund_type = 'CON'
ef_inst.get_curve()
# ef_inst.adjust_normal()
# ef_inst.get_data_matrix()