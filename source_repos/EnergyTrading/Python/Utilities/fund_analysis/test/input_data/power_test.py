from fund_analysis.input_data.power import Power
import pandas as pd
import datetime as dt

base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['W_1', 'W_2', 'M_1', 'M_2']
market_list = ['de', 'fr', 'hu', 'cz', 'sk', 'at']
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
params_dict['eD'] = dt.datetime(2024,12,3)
params_dict['ns'] = 2
params_dict['cont'] = False

inst = Power(params_dict)

# ef_inst.fund_type = 'CON'
# gas_inst.get_futures_curve()
# gas_inst.get_da_data()
# gas_inst.update_live_prices_from_file()
inst.get_da_data()