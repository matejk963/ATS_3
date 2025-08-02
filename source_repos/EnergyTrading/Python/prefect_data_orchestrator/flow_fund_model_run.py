from prefect import task, flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
import datetime as dt
import pandas as pd

import pickle


from Utilities.fund_analysis.fund_analysis.fair_value_manager import FairValueManager

@flow(timeout_seconds=1800, retries=3, retry_delay_seconds=300, log_prints=True, )
def fund_model_run(base_products,
                    market_list,
                    delivery_list):
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
    

    fcst_range = pd.date_range(start=pd.to_datetime(params_dict['eD'].strftime('%Y-%m-%d')),
                            end=pd.to_datetime(params_dict['eD'].strftime('%Y-%m-%d')),
                            freq='B')
    inst = FairValueManager(params_dict=params_dict,
                        fcst_range=fcst_range)
    
    model_params_dict = {}
    scen_list = []
    master_params_dict = {}
    master_params_dict['ResidualDemand'] = {'params': {
                                        'fund_type': 'ResidualDemand',
                                        'params_dict': params_dict},
                                    'scen_type': {'historical' : scen_list}}
    master_params_dict['AvailableCapacityData'] = {'params': {
                                        'params_dict': params_dict},
                                    'scen_type': {'historical' : scen_list}}
    
    inst.get_fcst_curves(model_params_dict=model_params_dict,
                    return_test_data=True,
                    master_params_dict=master_params_dict)



if __name__ == '__main__':
    # Optionally pass parameters if needed
    result = fund_model_run(
        base_products= ['M_1', 'M_2', 'M_3', 'M_4', 'M_5', 'M_6',
                          'Q_1', 'Q_2', 'Q_3', 'Q_4', 'Q_5', 'Q_6', 'Q_7', 'Q_8',
                          'Y_1', 'Y_2'],
        market_list= ['de'],
        delivery_list= ['base', 'peak']
    )
    print(result)



