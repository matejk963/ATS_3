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
# from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class_backup_act import RldMonitor as RM
from Spot.Monitor_class_backup_act import AvCapMonitor as AM
from Spot.Monitor_class_backup_act import SettleMonitor as SM

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from xgboost import XGBRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.preprocessing import StandardScaler

import statsmodels.api as sm



sD = datetime(2013,1,1)
eD = datetime(2024,3,17)
mon_inst = RM()
am_inst = AM()
mon_inst.set_date_range(sD, eD)
am_inst.set_date_range(sD, eD)

curve_date = dt.datetime(2024,2,20)

# av_cap = am_inst.get_data_fcst(market='de', forecast_date=curve_date,
#                   sD=dt.datetime(2024,4,1),
#                   eD=dt.datetime(2024,4,30))

# transition_matrix = mon_inst.get_transition_matrix(market='de',
#                                                    source='local',
#                                                    states=10)

# rld_curve = mon_inst.get_rld_curve()

scenario_df = mon_inst.get_timeseries_scenarios(market='de', days_fwd_list=[5], source='local',
                                                curve_fcst_date=curve_date, runs=200)

# scen_dict = mon_inst.simulate_multiple_scenarios(days_fwd_list=[5],
#                                     source='local', runs=200)


    



