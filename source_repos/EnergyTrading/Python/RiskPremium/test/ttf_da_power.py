# -*- coding: utf-8 -*-
"""
Created on Mon Sep  4 16:11:20 2023

@author: krajcovic
"""

from Database.TPData import TPData as tpd
from RiskPremium import RP_Tools as rpt
import Loaders.RLD_fetch as rf
from RiskPremium.RP_Tools import MFR, Plot2v2a, calculate_return,\
    TP_trades_data, df_from_tp_data_dict, ttf_settle_data
from Database import DB_reader as dbr

import refinitiv.data as rd


from Loaders.EikonSpot_class import EikonSpot as ES
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from datetime import time
import seaborn as sns
import refinitiv.data as rd
import pytz

from Database.TPData import TPData

import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass

data_class = TPData()
data_class.create_connection('OracleSQL')
start_date = dt.datetime(2023,7,1)
end_date = dt.datetime(2023,9,1)



date_range = pd.date_range(start=start_date,
                            end=end_date)
# for date in date_range:
    
    
    
bT = dt.datetime(2023,8,28)
eT = bT + dt.timedelta(days=1)
da_date = bT + dt.timedelta(days=1)
test = data_class.get_trades('ttf', 'DA', ['eex'],
                            da_date, bT, eT, 'base')