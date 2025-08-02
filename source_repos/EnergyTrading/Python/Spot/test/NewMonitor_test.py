# -*- coding: utf-8 -*-
"""
Created on Fri Feb 16 16:38:33 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

from Spot.Monitor_class import FuturesMonitor, SettleMonitor
from Database.DB_reader import Database


params_dict = {}

params_dict['market_list'] = ['gas']
# params_dict['market_list'] = ['coal']
params_dict['product_list'] = ['M.5']
params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
params_dict['year_list'] = [2024] * len(params_dict['product_list'])
params_dict['sD'] = datetime(2018,1,1)
params_dict['eD'] = datetime(2024,2,20)
params_dict['cont'] = False


# fut_inst = FuturesMonitor(params_dict)
settle_inst = SettleMonitor(params_dict)



# spot_data = settle_inst.get_final_settlement()
gsa_spot = settle_inst.get_spot_data_raw()
gas_spot = gsa_spot.resample('D').mean()
gas_spot.reset_index(inplace=True)
gas_spot.columns = ['datetime', 'settlement_price']

country = 'ttf_spot'
db = Database()



gas_spot.to_sql(name="stage_" + country ,
                  schema='futures',
                  con=db.connection_string,
                  if_exists='replace', index=False)
db.merge_from_staging_to_prod('futures', f"{country}")

# liq_data = {}

# for year in range(2015,2025):
#     params_dict['year_list'] = [year]*len(params_dict['product_list'])
#     params_dict['sD'] = datetime(year-1,9,1)
#     params_dict['eD'] = datetime(year,6,30)
#     fut_inst = FuturesMonitor(params_dict)
#     spread = fut_inst.spread_maker(diff='rel')
#     liq_data[year] = spread

# for year, df in liq_data.items():
#     plt.plot(range(len(df)), df.iloc[:,-1], label=str(year))
#     plt.legend()
# plt.grid()
