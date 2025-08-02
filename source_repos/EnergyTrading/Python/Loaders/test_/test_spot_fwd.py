# -*- coding: utf-8 -*-
"""
Created on Wed Jul 12 15:49:07 2023

@author: Marek
"""

from datetime import datetime, timedelta
import pandas as pd

import sys
sys.path.append('X:\\Loaders')
from EikonSpot_class import EikonSpot


path = 'C:/Users/Marek/Documents/Trading/Data/Price/EEX/'

bT = datetime(2023, 6, 1)
eT = datetime(2023, 7, 12) - timedelta(hours=1)

date_range = pd.date_range(bT, eT, freq='D')

mkt_list = ['de', 'at', 'hu', 'cz', 'sk', 'fr', 'be', 'nl']
dict_df_fwd = {}
df_spot = pd.DataFrame()
spot_sD = datetime(bT.year, bT.month, 1)
for m in mkt_list:
    eikon_spot = EikonSpot(m, bT.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    df_aux = eikon_spot.prices_df()
    df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    dict_df_fwd[m] = eikon_spot.fwd_df(date_range, ['M_0', 'M_1'], ['base'] * 2)

xx = eikon_spot.fwd_df_rel(bT, eT, ['M_0', 'M_1'], ['base'] * 2)


df_spot.to_csv(path + 'spot.csv')
[dict_df_fwd[m].to_csv(path + 'fwd_' + m + '.csv') for m in mkt_list]