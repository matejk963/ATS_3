# -*- coding: utf-8 -*-
"""
Created on Wed Aug  2 08:46:00 2023

@author: Marek
"""

import pandas as pd
from datetime import datetime, timedelta

from Loaders.loader_web import JaoLoader
from BorderSpread.portfolio_sim import capaStratSim
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
from BorderSpread.capacity_class import ImplicitCapacity
from BorderSpread.border_class import DataBorderClass
from Curve.forwardCurve import forward
from Loaders.EikonSpot_class import EikonSpot
from Utilities.date_functions import start_date
from Database.DB_reader import Database


bT = datetime(2023, 7, 25)
eT = datetime(2023, 9, 1) - timedelta(hours=1)
date_range = pd.date_range(bT, eT, freq='D')
sD = start_date(bT, 'M_1')

### Capas ###
jao = JaoLoader()
jao_dict = jao.single_ac_loader('etc', sD, 'm')
aux_dict = {b: (p, m) for b, p, m in
            zip(jao_dict['border'], jao_dict['auct_price'], jao_dict['maintenances'])}
border = ['ro_bg', 'at_de', 'de_at', 'de_be', 'be_de', 'be_nl', 'nl_be', 'de_nl', 'nl_de',
          'cz_de', 'cz_at', 'at_hu', 'hu_at', 'fr_be', 'fr_de', 'nl_dkw', 'de_dke',
          'dkw_dke', 'dke_dkw']
border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2023, 1, 1)
end_d = datetime(2023, 8, 1) - timedelta(hours=1)

capa_list = []
price_list = [aux_dict[b][0] for b in border]
m_list = [aux_dict[b][1] for b in border]

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

fwd_list = [forward('de', 84.64, sD, 'M', 'base'),
            forward('de', 86.71, sD, 'M', 'base'),
            forward('at', 88.05, sD, 'M', 'base'),
            forward('hu', 97.32, sD, 'M', 'base'),
            forward('cz', 89.75, sD, 'M', 'base'),
            forward('fr', 80.16, sD, 'M', 'base')]
fwd_pos_list = [11, -5, -6, -5, 3, 2]

###

### Load data for spot & futures
mkt_list_s = ['de', 'at', 'ro', 'cz', 'bg', 'hu', 'fr', 'be', 'nl', 'dkw', 'dke']
dict_df_fwd = {}

spot_sD = datetime(bT.year, bT.month, 1)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                     _from=spot_sD.strftime('%Y-%m-%d'),
                                     _to=eT.strftime('%Y-%m-%d'))
#df_spot = pd.DataFrame([])
for m in mkt_list_s:
    
    eikon_spot = EikonSpot( m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    #df_aux = eikon_spot.prices_df()
    #df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    #dict_df_fwd[m] = eikon_spot.fwd_df_rel(bT, eT, ['M_0', 'M_1'], ['base'] * 2)
# dict_df_fwd['si'] = dict_df_fwd['hu']

# Contract Lists
c_contr_list = [CapacityContr(c, p, 'base', sD, 'M', maintenance=m)
                for c, p, m in zip(capa_list, price_list, m_list)]
f_contr_list = [FwdContract(x, v) for x, v in zip(fwd_list, fwd_pos_list)]
# Strategy class
capa_strat = capaStratSim()
[capa_strat.add_contract(c) for c in c_contr_list]
[capa_strat.add_contract(c) for c in f_contr_list]

out_dict = capa_strat.simulate(date_range, df_spot, dict_df_fwd)

xx = out_dict['de_at'] - (3 / 5)*(out_dict['atmb2308s'] - out_dict['demb2308l'])
'''
cap = (0 * out_dict['ro_bg'] + 12 * out_dict['at_de'] + 12 * out_dict['de_at'] +
       2 * out_dict['de_be'] + 2 * out_dict['be_de'] + 4 * out_dict['be_nl'] + 4 * out_dict['nl_be'] +
       2 * out_dict['de_nl'] + 2 * out_dict['nl_de'] +
       5 * out_dict['cz_de'] + 6 * out_dict['cz_at'] + 7 * out_dict['at_hu'] + 6 * out_dict['hu_at'] +
       3 * out_dict['fr_be'] + 3 * out_dict['fr_de'])
hdg = (6 * out_dict['de'] - 5 * out_dict['hu'] - 6 * out_dict['at'] + 3 * out_dict['cz'] +
       2 * out_dict['fr'])
'''
hdg = pd.DataFrame([])
for c, v in zip(f_contr_list, fwd_pos_list):
    if hdg.empty:
        hdg = out_dict[c.contr_name] * v
    else:
        hdg += out_dict[c.contr_name] * v

vol_list = [12, 12, 12, 2, 2, 4, 4, 2, 2, 5, 6, 7, 6, 3, 3,4,1,3,2]
cur_df = pd.DataFrame({k: out_dict[k].iloc[-1, :] * v * 24 * 31 for k, v in zip(border, vol_list)}).T
print(cur_df)
print('\n\n')
print(hdg * 24 * 31)
print('\n\n')

pnl_df_c = pd.DataFrame({k: out_dict[k].iloc[:, 0] * v * 24 * 31 for k, v in zip(border, vol_list)}).T.sum()
pnl_df_c.name = 'capPnl'
pnl_df_h = hdg.iloc[:, 0] * 24 * 31
pnl_df_h.name = 'hdgPnl'
print(pd.concat([pnl_df_c, pnl_df_h, pnl_df_c + pnl_df_h], axis=1))