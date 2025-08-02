# -*- coding: utf-8 -*-
"""
Created on Tue Jul 11 13:43:40 2023

@author: Marek
"""

import pandas as pd
from datetime import datetime, timedelta


import sys
sys.path.append('X:\\BorderSpread')
sys.path.append('X:\\Curve')
sys.path.append('X:\\Loaders')
from portfolio_sim import capaStratSim
from capacity_contract_class import CapacityContr, FwdContract
from capacity_class import ImplicitCapacity
from border_class import DataBorderClass
from forwardCurve import forward
from EikonSpot_class import EikonSpot
from date_functions import start_date


bT = datetime(2023, 6, 22)
eT = datetime(2023, 8, 1) - timedelta(hours=1)
date_range = pd.date_range(bT, eT, freq='D')


### Capas ###
price_list = [2.73, 1.77, 1.13, 2.55, 2.03, 3.59, 3.67, 1.37, 3.36, 2.46, 3.37, 4.19, 2.0]
border = ['at_si', 'at_cz', 'cz_at', 'cz_sk', 'de_at', 'de_fr', 'fr_de', 'fr_be', 'be_fr', 'be_nl', 'nl_be', 'nl_de', 'de_nl']
border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2023, 1, 1)
end_d = datetime(2023, 7, 1) - timedelta(hours=1)

capa_list = []

bs_class = DataBorderClass(border, border_type, start_d, end_d)
bs_class.load_data()

data = dict()
for del_ in delivery_:
    data[del_] = bs_class.aggregate_data('M', delivery=del_)

for b in border:
    capacity = ImplicitCapacity([b], delivery_)
    for del_ in delivery_:
        capacity.capa_fit(data[del_], del_)
    capa_list.append(capacity)

sD = start_date(bT, 'M_1')

fwd_list = [forward('de', 100.71, sD, 'M', 'base'),
            forward('at', 103.22, sD, 'M', 'base'),
            forward('hu', 108.14, sD, 'M', 'base'),
            forward('cz', 103.62, sD, 'M', 'base')]

capa_contr_list = [CapacityContr(c, p, 'base', sD, 'M') for c, p in zip(capa_list, price_list)]
###

### Load data for spot & futures
mkt_list_s = ['de', 'at', 'si', 'cz', 'sk', 'hu', 'fr', 'be', 'nl']
dict_df_fwd = {}
df_spot = pd.DataFrame()
spot_sD = datetime(bT.year, bT.month, 1)
for m in mkt_list_s:
    eikon_spot = EikonSpot(m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    df_aux = eikon_spot.prices_df()
    df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    dict_df_fwd[m] = eikon_spot.fwd_df_rel(bT, eT, ['M_0', 'M_1'], ['base'] * 2)
# dict_df_fwd['si'] = dict_df_fwd['hu']

df_spot.fillna(method='ffill', inplace=True)

# Strategy class
capa_strat = capaStratSim()
[capa_strat.add_contract(CapacityContr(c, p, 'base', sD, 'M')) for c, p in zip(capa_list, price_list)]
[capa_strat.add_contract(FwdContract(x)) for x in fwd_list]

out_dict = capa_strat.simulate(date_range, df_spot, dict_df_fwd)

xx = out_dict['de_at'] - (3 / 5)*(out_dict['at'] - out_dict['de'])

cap = (5 * out_dict['at_si'] + 4 * out_dict['at_cz'] + 8 * out_dict['cz_at'] +
       6 * out_dict['cz_sk'] + 5 * out_dict['de_at'])
hdg = (8 * out_dict['de'] - 8 * out_dict['hu'] - 2 * out_dict['at'] + 2 * out_dict['cz'])

cap2 = (out_dict['de_fr'] + out_dict['fr_de'] + out_dict['fr_be'] + out_dict['be_fr'] +
        out_dict['be_nl'] + out_dict['nl_be'] + out_dict['nl_de'] + out_dict['de_nl'])

#out_dict['de_at'] - 0.5*(out_dict['at'] - out_dict['de'])
