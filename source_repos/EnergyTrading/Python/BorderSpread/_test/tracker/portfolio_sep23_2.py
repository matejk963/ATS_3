# -*- coding: utf-8 -*-
"""
Created on Mon Sep  4 09:10:28 2023

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


bT = datetime(2023, 8, 25)
eT = datetime(2023, 9, 10) - timedelta(hours=1)
date_range = pd.date_range(bT, eT, freq='D')
sD = start_date(bT, 'M_1')

### Capas ###
jao = JaoLoader()
jao_dict = jao.single_ac_loader('etc', sD, 'm')
aux_dict = {b: (p, m) for b, p, m in
            zip(jao_dict['border'], jao_dict['auct_price'], jao_dict['maintenances'])}

vol_dict = {'be_de': 2, 'de_be': 1, 'fr_be': 1, 'be_fr': 3, 'be_nl': 2,
            'fr_de': 6, 'de_fr': 3, 'de_nl': 3, 'nl_de': 2, 'dkw_nl': 1,
            'at_de': 8, 'de_at': 14, 'at_hu': 8}

border = list(vol_dict.keys())

border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2023, 1, 1)
end_d = datetime(2023, 9, 1) - timedelta(hours=1)

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

fwd_list = [forward('de', 97.66, sD, 'M', 'base'),
            forward('de', 102.30, sD, 'M', 'base'),
            forward('at', 101.97, sD, 'M', 'base'),
            forward('at', 105.84, sD, 'M', 'base'),
            forward('hu', 101.89, sD, 'M', 'base'),
            forward('fr', 100.91, sD, 'M', 'base')]
fwd_pos_list = [10, -4, 1, -4, -6, 3]

###

### Load data for spot & futures
mkt_list_s = ['de', 'at', 'hu', 'fr', 'be', 'nl', 'dkw']
dict_df_fwd = {}

spot_sD = datetime(bT.year, bT.month, 1)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                     _from=spot_sD.strftime('%Y-%m-%d'),
                                     _to=eT.strftime('%Y-%m-%d'))
#df_spot = pd.DataFrame([])
for m in mkt_list_s:
    
    eikon_spot = EikonSpot(m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    #df_aux = eikon_spot.prices_df()
    #df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    dict_df_fwd[m] = eikon_spot.fwd_df_rel(bT, eT, ['M_0', 'M_1'], ['base'] * 2)
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

xx = out_dict['de_at'] - (3 / 6)*(out_dict['atmb2309s'] - out_dict['demb2309l'])

hdg = pd.DataFrame([])
for c, v in zip(f_contr_list, fwd_pos_list):
    if hdg.empty:
        hdg = out_dict[c.contr_name] * v
    else:
        hdg += out_dict[c.contr_name] * v

cur_df = pd.DataFrame({k: out_dict[k].iloc[-1, :] * v * 24 * 30 for k, v in vol_dict.items()}).T
print(cur_df)
print('\n\n')
print(hdg * 24 * 30)
print('\n\n')

pnl_df_c = pd.DataFrame({k: out_dict[k].iloc[:, 0] * v * 24 * 30 for k, v in vol_dict.items()}).T.sum()
pnl_df_c.name = 'capPnl'
pnl_df_h = hdg.iloc[:, 0] * 24 * 30
pnl_df_h.name = 'hdgPnl'
print(pd.concat([pnl_df_c, pnl_df_h, pnl_df_c + pnl_df_h], axis=1))

border_list = []
settle_list = []

for key in vol_dict.keys():
    temp = out_dict[key]
    settle = temp['pnl'].iloc[-1]
    border_list.append(key)
    settle_list.append(settle)
settle_df = pd.DataFrame([border_list, settle_list]).T
settle_df.columns = ['capa', 'capa_settle']
settle_df = settle_df.set_index('capa')

# pnl report pre Peta
# tot_pnl = pd.concat([pnl_df_c, pnl_df_h, pnl_df_c + pnl_df_h], axis=1)
# tot_pnl.columns = ['capaPnL', 'hdgPnL', 'totPnL']

# with pd.ExcelWriter(r'c:\Users\krajcovic\Documents\Algo\temp\pnl_report_sep.xlsx',
#                     engine='xlsxwriter') as writer:
#     # Write df1 to a sheet named 'CustomName1'
#     tot_pnl.to_excel(writer, sheet_name='PnL')
    
#     # Write df2 to a sheet named 'CustomName2'
#     settle_df.to_excel(writer, sheet_name='CapaSettle')

#     # Get the xlsxwriter workbook and worksheet objects
#     workbook  = writer.book
#     worksheet1 = writer.sheets['PnL']

#     # Create a chart object
#     chart = workbook.add_chart({'type': 'line'})

#     # Configure the first series based on the data in the columns of df1
#     for i in range(1, len(tot_pnl.columns) + 1):
#         chart.add_series({
#             'name':       ['PnL', 0, i],
#             'categories': ['PnL', 1, 0, len(tot_pnl), 0],
#             'values':     ['PnL', 1, i, len(tot_pnl), i],
#         })

#     # Insert the chart into the worksheet
#     worksheet1.insert_chart('G1', chart) 