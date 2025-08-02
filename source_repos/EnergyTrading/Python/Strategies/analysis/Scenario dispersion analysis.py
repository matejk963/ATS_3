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
eD = datetime(2024,5,3)
mon_inst = RM()
am_inst = AM()
mon_inst.set_date_range(sD, eD)
am_inst.set_date_range(sD, eD)

curve_date = dt.datetime(2024,2,20)


mon_inst.compile_data() 
scen_dict = {}
for fcst_date in [dt.datetime(2024,5,2), dt.datetime(2024,5,3)]:
    scen_dict[fcst_date] = mon_inst.get_scenarios(market='de',
                                        scenario_type_list=['liq'],
                                        value_quantiles=10, hist_quantiles=3, 
                                        source='db', curve_fcst_date=fcst_date)



    



