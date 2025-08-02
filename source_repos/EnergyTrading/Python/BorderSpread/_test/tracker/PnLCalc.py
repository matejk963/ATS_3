# -*- coding: utf-8 -*-
"""
Created on Wed Jan 17 10:04:47 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from Loaders.EikonFut_class import EikonFut as EF
from Database.DB_reader import Database

sD = datetime(2024,1,15)
eD = datetime(2024,1,16)

product_list = ['M.1', 'M.2', 'M.3', 'Q.2', 'Q.3', 'Q.4']
year_list = [2024] * len(product_list)
delivery_list = ['base'] * len(year_list)

days_list = [31,29,31,91,92,92]
mwh_list = [day*24 for day in days_list]

markets = ['de', 'at', 'fr', 'cz', 'hu']
# markets = ['de']
fut_dict = {}
fut_df = pd.DataFrame()
for m in markets:
    ef_inst = EF(m)
    aux_df = ef_inst.fwd_df(sD, eD,
                            product_list,
                            delivery_list,
                            year_list)
    aux_df.columns = ['m1', 'm2', 'm3', 'q2', 'q3', 'q4']
    fut_dict[m] = aux_df.iloc[-1]
    fut_df[m] = aux_df.iloc[-1]
    

vol_dict = {'de_dke': 1, 'dkw_nl': 1, 'at_de': 5, 'be_de': 3,
            'be_nl': 3, 'de_at': 5, 'de_be': 3, 'de_nl': 3,
            'nl_be': 3, 'nl_de': 3, 'cz_de': 3, 'de_cz': 2,
            'at_hu': 2, 'hu_at': 2, 'at_cz': 2, 'cz_at': 2,
            'sk_cz': 1, 'hu_sk': 1, 'be_fr': 4, 'fr_be': 4}

price_dict = {'de_dke': 1.48, 'dkw_nl': 7.33, 'at_de': 1.49, 'be_de': 5.6,
            'be_nl': 3.96, 'de_at': 6.97, 'de_be': 5.11, 'de_nl': 4.36,
            'nl_be': 4.4, 'nl_de': 5.1, 'cz_de': 1.35, 'de_cz': 5.35,
            'at_hu': 6.89, 'hu_at': 1.71, 'at_cz': 2.01, 'cz_at': 3.88,
            'sk_cz': 0.8, 'hu_sk': 0.66, 'be_fr': 4.73, 'fr_be': 3.14}


border = list(vol_dict.keys())

### Load data for spot & futures
all_countries = [a.split('_')[0] for a in border] +\
                       [a.split('_')[1] for a in border]
mkt_list_s = []
for item in all_countries:
    if item not in mkt_list_s:
        mkt_list_s.append(item)

spot_sD = datetime(2024,1,1)
eT = datetime(2024,1,16)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                     _from=spot_sD.strftime('%Y-%m-%d'),
                                     _to=eT.strftime('%Y-%m-%d'))


pnl_dict = {}
for key, val in price_dict.items():
    c_out, c_in = key.split('_')
    aux = df_spot[[c_out, c_in]].copy()
    diff = aux[c_in] - aux[c_out]
    diff = np.mean([max(a,0) for a in diff])
    pnl = diff - val
    pnl_dict[key] = pnl
    

hours = ((eT-spot_sD).days+1)*24
tot_pnl_dict = {}
pnl_list = []
for key, val in pnl_dict.items():
    vol = vol_dict[key]
    pnl = pnl_dict[key]
    eur_pnl = hours * vol * pnl
    tot_pnl_dict[m] = eur_pnl
    pnl_list.append(eur_pnl)
    






