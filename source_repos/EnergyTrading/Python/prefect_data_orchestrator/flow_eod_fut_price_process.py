from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
import datetime as dt
import pandas as pd

import pickle


from Utilities.FuturesManager.FuturesManager import FuturesManager as FM

@flow(timeout_seconds=600, retries=3, retry_delay_seconds=300, log_prints=True, )
def EoD_fut_price_process(base_products,
                          market_list,
                          delivery_list,
                          file_path = r'C:\data\Data\Data\Futures\data_dict.pkl'):
    # Generate the combinations
    products = []
    markets = []
    delivery = []
    
    for product in base_products:
        for market in market_list:
            for delivery_option in delivery_list:
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
    fm_inst = FM(params_dict)   
    data_dict = fm_inst.analyze_data()

    file_path = r'C:\data\Data\Data\Futures\data_dict.pkl'

    with open(file_path,'wb') as f:
        pickle.dump(data_dict, f)
    



   


