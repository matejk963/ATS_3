# -*- coding: utf-8 -*-

"""
Created on Wed Jan 17 14:41:55 2024

@author: krajcovic
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
import pickle

# from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import AvCapMonitor as AM
from Spot.Monitor_class import SettleMonitor as SM

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from xgboost import XGBRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.preprocessing import StandardScaler

import statsmodels.api as sm



sD = datetime(2020,1,1)
eD = datetime(2024,7,1)
mon_inst = RM()
am_inst = AM()
mon_inst.set_date_range(sD, eD)
am_inst.set_date_range(sD, eD)

scen_dict = {}

fcst_range = pd.date_range(start=dt.datetime(2023,7,12), end=dt.datetime(2023,7,12))

for fcst_date in fcst_range:

    aux_dict = mon_inst.simulate_multiple_scenarios(markets=['de', 'fr', 'be', 'nl'],
                                                      scenario_type_list=['liq'],
                                                      curve_fcst_date=fcst_date,
                                                      source='db', runs=200)
    scen_dict[fcst_date] = aux_dict
    

with open(r'Z:\Data\Scenarios\scen_dict_20240601_20240701.pickle', 'wb') as handle:
    pickle.dump(scen_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)

# # Specify the filename
# filename = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\rld_scen.pickle'

# # Save the dictionary to a pickle file
# with open(filename, 'wb') as file:
#     pickle.dump(scen_dict, file)


    



