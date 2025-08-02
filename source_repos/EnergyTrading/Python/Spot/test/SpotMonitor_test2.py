# -*- coding: utf-8 -*-
"""
Created on Thu May  9 10:13:20 2024

@author: krajcovic
"""

import pandas as pd
import datetime as dt
from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import AvCapMonitor as AM

sD = dt.datetime(2024,1,1)
eD = dt.datetime(2024,3,17)
mon_inst = RM()
am_inst = AM()
mon_inst.set_date_range(sD, eD)
am_inst.set_date_range(sD, eD)

# schema_name = 'FUND_AvailCap'

del_start = dt.datetime(2024,5,1)
del_end = dt.datetime(2024,5,31)

av_cap = am_inst.get_data_fcst(market='de',source='db', forecast_date=eD,
                               sD=del_start, eD=del_end)

# schema = 'FUND_ResidualDemand'
# rld_data = rm_inst.get_fund_data_db(schema=schema, sD_fcst=dt.datetime(2024,2,20),
#                                     eD_fcst=dt.datetime(2024,2,25))