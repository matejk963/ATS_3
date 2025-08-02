# -*- coding: utf-8 -*-
"""
Created on Tue Dec 19 10:50:58 2023

@author: Marek
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
date = datetime(2023, 12, 16)

all_countries = [a.split('_')[0] for a in border] +\
                       [a.split('_')[1] for a in border]
countries = []
for item in all_countries:
    if item not in countries:
        countries.append(item)

f_dict = {}
for country in countries:
    f_dict[country] = {}
    efut = EF(country)
    product_list = ['M_1', 'M_2', 'M_3', 'Q_2', 'Q_3', 'Q_4', 'Y_1']
    delivery_list = ['base'] * len(product_list)
    year_list = [None] * len(product_list)
    
    country_df = efut.fwd_df(sD=(date-timedelta(days=2)),
                           eD=date,
                           product_list=product_list,
                           delivery_list=delivery_list,
                           year_list=year_list)
    f_dict[country] = []
    for product, col in zip(product_list, country_df.columns):
        f_dict[country].append(forward(country,
                                   country_df[col][0],
                                   start_date(date, product),
                                   product.split('_')[0],
                                   'base'))
        
        
               
                       

# f_dict = {'de': [forward('de', 10, start_date(date, 'M_1'), 'M', 'base'),
#                  forward('de', 18, start_date(date, 'M_2'), 'M', 'base'),
#                  forward('de', 11, start_date(date, 'M_3'), 'M', 'base'),
#                  forward('de', 14, start_date(date, 'Q_1'), 'Q', 'base'),
#                  forward('de', 12, start_date(date, 'Q_2'), 'Q', 'base'),
#                  forward('de', 9, start_date(date, 'Y_1'), 'Y', 'base')],
#           'cz': [forward('cz', 10, start_date(date, 'M_1'), 'M', 'base'),
#                  forward('cz', 8, start_date(date, 'M_2'), 'M', 'base'),
#                  forward('cz', 11, start_date(date, 'M_3'), 'M', 'base'),
#                  forward('cz', 14, start_date(date, 'Q_1'), 'Q', 'base'),
#                  forward('cz', 12, start_date(date, 'Q_2'), 'Q', 'base'),
#                  forward('cz', 9, start_date(date, 'Y_1'), 'Y', 'base')]}

date_aux = datetime(2024, 1, 1)
curve_dict = {k: rawCurve(v) for k, v in f_dict.items()}
fw_curve_dict = {k: [] for k in curve_dict.keys()}
for m, c in curve_dict.items():
    c.rem_arbitrage()
    fw_curve_dict[m] = c.create_curve_pd().loc[date_aux:]
    
#idx_ser = pd.date_range(sD, eD, freq='H')
#fw_curve_dict = {'cz': pd.Series([20] * len(idx_ser), index=idx_ser),
#                 'de': pd.Series([20] * len(idx_ser), index=idx_ser)}
 
pos = posCapaClass.delta(fw_curve_dict)
hedgeContr = FwdContract(forward('cz', 10, start_date(date, 'M_2'), 'M', 'base'))

posHedgeClass = None
vol_hdg = [3, -2, 1, -1, -1]
vol_hdg = [1, -2, -1, 2, 2, -1, -1, -1, 1, 4, -1, -2, 1, -1, -1]
# vol_hdg = [0,0,0,0,0]
hC_list = []
hC_list.append(FwdContract(forward('de', 86.81, datetime(2024,1,1), 'M', 'base')))
hC_list.append(FwdContract(forward('de', 86.09, datetime(2024,1,1), 'M', 'base')))
hC_list.append(FwdContract(forward('cz', 91.81, datetime(2024,1,1), 'M', 'base')))
hC_list.append(FwdContract(forward('fr', 84.09, datetime(2024,1,1), 'M', 'base')))
hC_list.append(FwdContract(forward('de', 88.02, datetime(2024,1,1), 'Q', 'base')))
hC_list.append(FwdContract(forward('cz', 93.75, datetime(2024,1,1), 'Q', 'base')))
hC_list.append(FwdContract(forward('hu', 98.14, datetime(2024,1,1), 'Q', 'base')))
hC_list.append(FwdContract(forward('de', 92.35, datetime(2024,7,1), 'Q', 'base')))
hC_list.append(FwdContract(forward('fr', 87.75, datetime(2024,7,1), 'Q', 'base')))
hC_list.append(FwdContract(forward('de', 106.64, datetime(2024,1,1), 'Y', 'base')))
hC_list.append(FwdContract(forward('de', 101.6, datetime(2024,1,1), 'Y', 'base')))
hC_list.append(FwdContract(forward('at', 112.78, datetime(2024,1,1), 'Y', 'base')))
hC_list.append(FwdContract(forward('cz', 105.4, datetime(2024,1,1), 'Y', 'base')))
hC_list.append(FwdContract(forward('hu', 115.45, datetime(2024,1,1), 'Y', 'base')))
hC_list.append(FwdContract(forward('fr', 113.55, datetime(2024,1,1), 'Y', 'base')))


# hC_list.append(FwdContract(forward('de', 105.85, datetime(2024,1,1), 'Y', 'base')))
# hC_list.append(FwdContract(forward('de', 86.06, datetime(2024,1,1), 'M', 'base')))
# hC_list.append(FwdContract(forward('de', 87.44, datetime(2024,1,1), 'Q', 'base')))
# hC_list.append(FwdContract(forward('de', 92.35, datetime(2024,7,1), 'Q', 'base')))
# hC_list.append(FwdContract(forward('at', 112.78, datetime(2024,1,1), 'Y', 'base')))
# hC_list.append(FwdContract(forward('cz', 105.4, datetime(2024,1,1), 'Y', 'base')))
# hC_list.append(FwdContract(forward('hu', 115.45, datetime(2024,1,1), 'Y', 'base')))
# hC_list.append(FwdContract(forward('fr', 113.55, datetime(2024,1,1), 'Y', 'base')))
# hC_list.append(FwdContract(forward('fr', 84.06, datetime(2024,1,1), 'M', 'base')))
for h_c, v in zip(hC_list, vol_hdg):
    if posHedgeClass is None:
        posHedgeClass = PositionManagerHedge(h_c, v)
    else:
        posHedgeClass.merge(PositionManagerHedge(h_c, v))
pos_capa = posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)
q_dict = pd.DataFrame({k: v.resample('QS').mean() for k, v in fw_curve_dict.items()})



# posHedgeClass = PositionManagerHedge(hedgeContr, 0)
# posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)