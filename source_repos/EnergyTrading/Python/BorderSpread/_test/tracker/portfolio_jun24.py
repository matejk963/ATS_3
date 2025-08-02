# -*- coding: utf-8 -*-
"""
Created on Mon Dec  4 09:39:41 2023

@author: Marek
"""

import pandas as pd
from datetime import datetime, timedelta
import numpy as np

from Loaders.loader_web import JaoLoader
from BorderSpread.portfolio_sim import capaStratSim
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
from BorderSpread.capacity_class import ImplicitCapacity
from BorderSpread.border_class import DataBorderClass
from Curve.forwardCurve import forward
from Loaders.EikonSpot_class import EikonSpot
from Utilities.date_functions import start_date
from Database.DB_reader import Database


def calculate_average_volume(transactions):
    positive_volume_sum = sum(p * v for v, p in transactions if v > 0)
    negative_volume_sum = sum(p * -v for v, p in transactions if v < 0)
    positive_count = sum(v for v, _ in transactions if v > 0)
    negative_count = sum(-v for v, _ in transactions if v < 0)
    positive_average = positive_volume_sum / positive_count if positive_count > 0 else 0
    negative_average = negative_volume_sum / negative_count if negative_count > 0 else 0
    out_p = [positive_average, negative_average]
    out_v = [positive_count, -negative_count]
    return out_p, out_v


bT = datetime(2024, 5, 28)
eT = datetime(2024, 7, 1) - timedelta(hours=1)

date_range = pd.date_range(bT, eT, freq='D')
sD = start_date(bT, 'M_1')

### Capas ###
jao = JaoLoader()
# jao_dict = jao.single_ac_loader('etc', sD, 'y')
# aux_dict = {b: (p, m) for b, p, m in
#             zip(jao_dict['border'], jao_dict['auct_price'], jao_dict['maintenances'])}

vol_dict = {'at_de': 5, 'be_de': 3,
            'be_nl': 3, 'de_at': 5, 'de_be': 3, 'de_nl': 3,
            'nl_be': 3, 'nl_de': 3, 'cz_de': 3, 'de_cz': 2,
            'at_hu': 2, 'hu_at': 2, 'at_cz': 2, 'cz_at': 2,
            'sk_cz': 1, 'hu_sk': 1, 'be_fr': 4, 'fr_be': 4,
            'dkw_nl': 1, 'de_dke': 1}

price_dict = {'at_de': 1.49, 'be_de': 5.6,
            'be_nl': 3.96, 'de_at': 6.97, 'de_be': 5.11, 'de_nl': 4.36,
            'nl_be': 4.4, 'nl_de': 5.1, 'cz_de': 1.35, 'de_cz': 5.35,
            'at_hu': 6.89, 'hu_at': 1.71, 'at_cz': 2.01, 'cz_at': 3.88,
            'sk_cz': 0.8, 'hu_sk': 0.66, 'be_fr': 4.73, 'fr_be': 3.14,
            'dkw_nl': 7.33, 'de_dke': 1.48}

aux_dict = {b: (p, []) for b, p in price_dict.items()}

border = list(vol_dict.keys())

border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2023, 1, 1)
end_d = datetime(2023, 12, 31) - timedelta(hours=1)

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
#Hedged positions dict
positions_ = {}
for country in ['de', 'fr', 'cz', 'hu', 'at']:
    positions_[country] = {}
    
positions_['de'] = {'M': {'base': {datetime(2024,6,1): [[-1, 71.69],
                                                        [-1, 71.95],
                                                        [1, 73.52],
                                                        [1, 63.74],
                                                        [-1, 56.41],
                                                        [-1, 74.45],
                                                        [-1, 76.2],
                                                        [-1, 81.08],
                                                        [1, 78.65],
                                                        [-1, 72.89],
                                                        [1, 63.6],
                                                        [1, 57.05],
                                                        [-1, 52.38],
                                                        [-1, 52.35],
                                                        [1, 53.3],
                                                        [-1, 55.71],
                                                         [1, 107.95],
                                                         [1, 109],
                                                         [1, 104.85],
                                                         [1,104.75],
                                                         [-1, 101.6]]}}}
positions_['cz'] = {'M': {'base': {datetime(2024,6,1): [[-1, 81.25],
                                                        [-1, 66.1],
                                                        [-1, 56.8],
                                                      [1, 105.4]]}}}

positions_['fr'] = {'M': {'base': {datetime(2024,6,1): [[1, 40.23],
                                                        [1, 44.95],
                                                        [-1, 42.27],
                                                        [-1, 39.99],
                                                        [1, 70],
                                                        [1, 71.6],
                                                        [1, 75.58],
                                                        [1, 67.49],
                                                        [1, 46.35],
                                                       [-1, 113.55]]}}}
positions_['hu'] = {'M': {'base': {datetime(2024,6,1): [[-1, 63.05],
                                                        [1, 57.43],
                                                       [-1, 115.45]]}}}
positions_['at'] = {'M': {'base': {datetime(2024,6,1): [[1, 55.41],
                                                        [1, 56.91],
                                                        [-1, 115],
                                                       [-1, 110.55]]}}}


positions = {}
for market, market_data in positions_.items():
    for product, product_data in market_data.items():
        positions[market] = {product: {}}
        for base, base_data in product_data.items():
            positions[market][product][base] = {}
            for date, transactions in base_data.items():
                p_list, v_list = calculate_average_volume(transactions)
                positions[market][product][base][date] = [[v, p] for p, v in
                                                          zip(p_list, v_list)
                                                          if abs(v) > 0]


fwd_pos_list = []
fwd_list = []
buy_dict = {}
sell_dict = {}
for country, count_dict in positions.items():
    buy_dict[country] = {}
    sell_dict[country] = {}
    for product, prod_dict in count_dict.items():
        for delivery, del_dict in prod_dict.items():
            for tenor, tenor_lists in del_dict.items():
                buy_vol_list = []
                buy_price_list = []
                sell_vol_list = []
                sell_price_list = []
                for pos in tenor_lists:
                    vol, price = pos
                    fwd_pos_list.append(vol)
                    fwd_list.append(forward(country,
                                            price,
                                            tenor,
                                            product,
                                            delivery))
          
                    


# fwd_list = [forward('de', 98.001, sD, 'M', 'base'),
#             forward('de', 98.56, sD, 'M', 'base'),
#             forward('at', 105.74, sD, 'M', 'base'),
#             forward('cz', 103.01, sD, 'M', 'base'),
#             forward('hu', 101.5, sD, 'M', 'base')]
# fwd_pos_list = [10, -2, -9, 2, -1]

###

### Load data for spot & futures
all_countries = [a.split('_')[0] for a in border] +\
                       [a.split('_')[1] for a in border]
mkt_list_s = []
for item in all_countries:
    if item not in mkt_list_s:
        mkt_list_s.append(item)
# mkt_list_s = ['de', 'hu', 'cz', 'sk', 'at', 'be', 'nl', 'dkw', 'dke', 'ro']
dict_df_fwd = {}

spot_sD = datetime(bT.year, bT.month, 1)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                      _from=spot_sD.strftime('%Y-%m-%d'),
                                      _to=eT.strftime('%Y-%m-%d'))
# df_spot = pd.DataFrame([])
for m in mkt_list_s:
    
    eikon_spot = EikonSpot(m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    # df_aux = eikon_spot.prices_df()
    # df_spot = pd.concat([df_spot, df_aux], axis=1)
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

# capa_strat1 = capaStratSim()
# [capa_strat1.add_contract(c) for c in f_contr_list]
# out_dict1 = capa_strat1.simulate(date_range, df_spot, dict_df_fwd)

"""
xx = out_dict['de_at'] - (5 / 7)*(out_dict['atmb2310s'] - out_dict['demb2310l'])
xy = out_dict['de_at'] + out_dict['at_hu'] - (5 / 7)*(out_dict['humb2310s'] - out_dict['demb2310l'])
xz = (out_dict['de_cz'] + (10 / 8) * out_dict['cz_de']
      - (5 / 7)*(out_dict['czmb2310s'] - out_dict['demb2310l']))
"""

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

mtm_capa = pd.DataFrame({k: out_dict[k].iloc[:, 1] * v * 24 * 30 for k, v in vol_dict.items()}).sum(axis=1)
mtm_hdg = hdg.iloc[:, 1] * 24 * 30

tot_pnl = pd.concat([pnl_df_c, pnl_df_h, pnl_df_c + pnl_df_h], axis=1)
tot_pnl.columns = ['capaPnL', 'hdgPnL', 'totPnL']

tot_mtm = pd.concat([mtm_capa, mtm_hdg, mtm_capa + mtm_hdg], axis=1)
tot_mtm.columns = ['capaMtM', 'hdgMtM', 'totMtM']

print(pd.DataFrame([pd.DataFrame({k: out_dict[k].loc[d, :] * v * 24 * 30
                                  for k, v in vol_dict.items()}).T.sum().sum() + (hdg.loc[d, :] * 24 * 31).sum().sum()
                    for d in hdg.index[2:]], index=hdg.index[2:]))

name = sD.strftime('%y%b') + '_' + eT.strftime('%m%d')
with pd.ExcelWriter(r'//etc-dc2k19/net/capa/report/' + name + '.xlsx',
                    engine='xlsxwriter') as writer:
    # Write df1 to a sheet named 'CustomName1'
    tot_pnl.to_excel(writer, sheet_name='PnL')
    
    # Write df2 to a sheet named 'CustomName2'
    settle_df.to_excel(writer, sheet_name='CapaSettle')

    # Write df3 to a sheet named 'CustomName2'
    tot_mtm.to_excel(writer, sheet_name='MtM')

    # Get the xlsxwriter workbook and worksheet objects
    workbook  = writer.book
    worksheet1 = writer.sheets['PnL']

    # Create a chart object
    chart = workbook.add_chart({'type': 'line'})

    # Configure the first series based on the data in the columns of df1
    for i in range(1, len(tot_pnl.columns) + 1):
        chart.add_series({
            'name':       ['PnL', 0, i],
            'categories': ['PnL', 1, 0, len(tot_pnl), 0],
            'values':     ['PnL', 1, i, len(tot_pnl), i],
        })

    # Insert the chart into the worksheet
    worksheet1.insert_chart('G1', chart)