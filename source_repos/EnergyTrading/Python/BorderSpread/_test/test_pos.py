#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 31 16:20:34 2023

@author: marek
"""


import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import BorderSpread.border_class as bc
from BorderSpread.PositionManager import PositionManagerCapa, PositionManagerHedge
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
import BorderSpread.capacity_class as capa
from Utilities.date_functions import end_date, start_date
from Curve.forwardCurve import forward, rawCurve

from Loaders.EikonFut_class import EikonFut as EF
import refinitiv.data as rd


border = ['de_hu', 'hu_de',
          'de_at', 'at_de', 'de_cz', 'cz_de', 'cz_at', 'at_cz',
          'hu_at', 'at_hu', 'sk_cz', 'hu_sk', 'de_fr', 'fr_de',
          'de_nl', 'nl_de', 'de_be', 'be_de', 'be_nl', 'nl_be',
          'be_fr', 'fr_be']
border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2021,1,1)
end_d = datetime(2023,12,1) - timedelta(hours=1)

dlvr = delivery_[0]
sD = datetime(2024,1,1)
eD = datetime(2025,1,1) - timedelta(hours=1)

price = 0
period = 'Y'

#kolko kapacity
vol_list = [2, 3,
            3, 3, 2, 2, 2, 2,
            0, 0, 0, 0, 4, 4,
            0,0,0,0,0,0,0,0]

# vol_list = [0,0,
#             5,5,2,3,2,2,
#             2,2,1,1,4,4,
#             0,0,0,0,0,0]

posCapaClass = None

bs_class = bc.DataBorderClass(border, border_type, start_d, end_d)
bs_class.load_data()

data = dict()
for del_ in delivery_:
    data[del_] = bs_class.aggregate_data('M', delivery=del_)

capacity_list = []
for b, v in zip(border, vol_list):
    capacity = capa.ImplicitCapacity([b], delivery_)
    
    for del_ in delivery_:
        capacity.capa_fit(data[del_], del_)
        # capacity.plot(data[del_], del_)
        
    capaContr = CapacityContr(capacity, price, dlvr, sD, period)

    if posCapaClass is None:
        posCapaClass = PositionManagerCapa(capaContr, v)
    else:
        posCapaClass.merge(PositionManagerCapa(capaContr, v))
    posCapaClass.cascade(len(posCapaClass.asset_list) - 1, 'M')


# Create forward curves
date = datetime(2024, 1, 2)

all_countries = [a.split('_')[0] for a in border] +\
                       [a.split('_')[1] for a in border]
countries = []
for item in all_countries:
    if item not in countries:
        countries.append(item)

f_dict = {}
f_dict2 = {}
for country in countries:
    f_dict[country] = {}
    efut = EF(country)
    rel_product_list = ['M_1', 'M_2', 'M_3', 'Q_2', 'Q_3', 'Q_4', 'Y_1']
    product_list = ['M.1', 'M.2', 'M.3', 'Q.2', 'Q.3', 'Q.4']
    delivery_list = ['base'] * len(product_list)
    # year_list = [None] * len(product_list)
    year_list = [2024] * len(product_list)
    
    country_df = efut.fwd_df(sD=(date-timedelta(days=2)),
                           eD=date,
                           product_list=product_list,
                           delivery_list=delivery_list,
                           year_list=year_list)
    f_dict[country] = []
    f_dict2[country] = country_df
    for product, col in zip(rel_product_list, country_df.columns):
        if '.' in product:
            product = product.replace('.', '_')
        f_dict[country].append(forward(country,
                                   country_df[col][0],
                                   start_date(datetime(2023,12,20), product),
                                   product.split('_')[0],
                                   'base'))
        
        
               
                       

# f_dict = {'de': [forward('de', 10, start_date(date, 'M_1'), 'M', 'base')],
#           'cz': [forward('cz', 10, start_date(date, 'M_1'), 'M', 'base')]}

date_aux = datetime(2024, 1, 1)
curve_dict = {k: rawCurve(v) for k, v in f_dict.items()}
fw_curve_dict = {k: [] for k in curve_dict.keys()}
for m, c in curve_dict.items():
    c.rem_arbitrage()
    fw_curve_dict[m] = c.create_curve_pd().loc[date_aux:]
    
#idx_ser = pd.date_range(sD, eD, freq='H')
#fw_curve_dict = {'cz': pd.Series([20] * len(idx_ser), index=idx_ser),
#                 'de': pd.Series([20] * len(idx_ser), index=idx_ser)}

# posHedgeClass = None
# vol_hdg = [2, 2, 2]
# hC_list = []
# hC_list.append(FwdContract(forward('cz', 10, start_date(date, 'M_2'), 'M', 'base')))
# hC_list.append(FwdContract(forward('de', 10, start_date(date, 'M_2'), 'M', 'base')))
# hC_list.append(FwdContract(forward('fr', 10, start_date(date, 'M_2'), 'M', 'base')))
# for h_c, v in zip(hC_list, vol_hdg):
#     if posHedgeClass is None:
#         posHedgeClass = PositionManagerHedge(h_c, v)
#     else:
#         posHedgeClass.merge(PositionManagerHedge(capaContr, v))
# posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)

# pos = posCapaClass.delta(fw_curve_dict)
# hedgeContr = FwdContract(forward('cz', 10, start_date(date, 'M_2'), 'M', 'base'))

#Hedged positions dict
positions = {}
for country in ['de', 'fr', 'cz', 'hu', 'at']:
    positions[country] = {}
    
positions['de'] = {'M': {'base': {datetime(2024,1,1):[[1, 86.81],
                                                      [-1, 86.06],
                                                      [-1, 86.11]]}},
                   'Q': {'base': {datetime(2024,1,1): [[1, 88.6],
                                                       [1, 87.44],
                                                       [1, 82.31]],
                                 datetime(2024,4,1): [[-1, 74.45],
                                                      [-1, 76.2],
                                                       [-1, 81.08]],
                                 datetime(2024,7,1): [[-1, 92.35],
                                                      [-1, 90.25]],
                                 datetime(2024,10,1): [[1, 105.5]]}},
                   'Y': {'base': {datetime(2024,1,1): [[1, 107.95],
                                                      [1, 109],
                                                      [1, 104.85],
                                                      [1,104.75],
                                                      [-1, 101.6]]}}}
positions['cz'] = {'M': {'base': {datetime(2024,1,1): [[-1, 91.81]]}},
                   'Q': {'base': {datetime(2024,1,1): [[-1, 93.75]]}},
                   'Y': {'base': {datetime(2024,1,1): [[1, 105.4]]}}}

positions['fr'] = {'M': {'base': {datetime(2024,1,1): [[1, 84.11],
                                                       [1, 84.06]]}},
                   'Q': {'base': {datetime(2024,4,1): [[1, 70],
                                                       [1, 71.6],
                                                        [1, 75.58]],
                                 datetime(2024,7,1): [[1, 87.75],
                                                      [1, 84.95]],
                                 datetime(2024,10,1): [[-1, 110.9]]}},
                   'Y': {'base': {datetime(2024,1,1): [[-1, 113.55]]}}}
positions['hu'] = {'Q': {'base': {datetime(2024,1,1): [[-1, 98.14]]}},
                    'Y': {'base': {datetime(2024,1,1): [[-1, 115.45]]}}}
positions['at'] = {'Q': {'base': {datetime(2024,1,1): [[-1, 89.51]]}},
                   'Y': {'base': {datetime(2024,1,1): [[-1, 115],
                                              [-1, 110.55]]}}}

vol_hdg = []
hC_list = []
for country, count_dict in positions.items():
    print(country)
    for product, prod_dict in count_dict.items():
        print(product)
        for delivery, del_dict in prod_dict.items():
            print(delivery)
            for tenor, tenor_lists in del_dict.items():
                print(tenor)
                for pos in tenor_lists:
                    vol, price = pos
                    print(vol, '/', price)
                    vol_hdg.append(vol)
                    hC_list.append(FwdContract(forward(country,
                                                       price,
                                                       tenor,
                                                       product,
                                                       delivery)))
            


posHedgeClass = None



for h_c, v in zip(hC_list, vol_hdg):
    if posHedgeClass is None:
        posHedgeClass = PositionManagerHedge(h_c, v)
    else:
        posHedgeClass.merge(PositionManagerHedge(h_c, v))
pos_capa = posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)
q_dict = pd.DataFrame({k: v.resample('QS').mean() for k, v in fw_curve_dict.items()})

delta_out = posHedgeClass.delta(fw_curve_dict, 'MS')
delta_out = delta_out.T.groupby(delta_out.T.index).sum().T

fw_quarts_dict = {}
for key, series in fw_curve_dict.items():
    fw_quarts_dict[key] = series.resample('Q').mean()

# posHedgeClass = PositionManagerHedge(hedgeContr, 0)
# posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)
