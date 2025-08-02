#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 31 16:20:34 2023

@author: marek
"""


import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import BorderSpread.border_class as bc
from BorderSpread.PositionManager import PositionManagerCapa, PositionManagerHedge
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
import BorderSpread.capacity_class as capa
from Utilities.date_functions import end_date, start_date
from Curve.forwardCurve import forward, rawCurve

from Loaders.EikonFut_backup_class import EikonFut as EF
from Database.DB_reader import Database

import refinitiv.data as rd


def get_price_vol(positions, market, month, year=2024):
    m_start = datetime(year, month, 1)
    m_end = m_start + relativedelta(months=1) - timedelta(days=1)
    mkt_dict = positions[market]
    buy_price, sell_price = [], []
    buy_vol, sell_vol = [], []

    for prod, prod_dict in mkt_dict.items():
        for bp, bp_dict in prod_dict.items():
            for date, data_list in bp_dict.items():
                # Determine the end date based on product type
                if prod == 'M':
                    date_end = date + relativedelta(months=1) - timedelta(days=1)
                elif prod == 'Q':
                    date_end = date + relativedelta(months=3) - timedelta(days=1)
                elif prod == 'Y':
                    date_end = date + relativedelta(months=12) - timedelta(days=1)
                
                # Check if the date falls within the specified month
                if date <= m_start <= date_end:
                    for data in data_list:
                        vol, price = data
                        if vol < 0:
                            sell_vol.append(abs(vol))
                            sell_price.append(price)
                        else:
                            buy_vol.append(vol)
                            buy_price.append(price)

    # Handle cases where buy_vol or sell_vol sum to zero
    if buy_vol:
        avg_buy_price = np.average(buy_price, weights=buy_vol)
        total_buy_vol = np.sum(buy_vol)
    else:
        avg_buy_price, total_buy_vol = 0, 0

    if sell_vol:
        avg_sell_price = np.average(sell_price, weights=sell_vol)
        total_sell_vol = np.sum(sell_vol)
    else:
        avg_sell_price, total_sell_vol = 0, 0

    return avg_buy_price, total_buy_vol, avg_sell_price, total_sell_vol
                    
                
                    



border = ['de_hu', 'hu_de',
          'de_at', 'at_de', 'de_cz', 'cz_de', 'cz_at', 'at_cz',
          'hu_at', 'at_hu', 'sk_cz', 'hu_sk', 'de_fr', 'fr_de',
          'de_nl', 'nl_de', 'de_be', 'be_de', 'be_nl', 'nl_be',
          'be_fr', 'fr_be']
border_type = ['implicit'] * len(border)
delivery_ = ['base']
# Historical data
start_d = datetime(2021,1,1)
end_d = datetime(2024,3,1) - timedelta(hours=1)

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




date = datetime(2024, 6, 26)


# date = today - timedelta(days=1)

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
    efut = EF(country, reference_date=date)
    rel_product_list = ['M_1', 'M_2', 'M_3', 'Q_2', 'Q_3', 'Q_4', 'Y_1']
    product_list = ['M.1', 'M.2', 'M.3', 'M.4', 'M.5', 'M.6', 'Q.3', 'Q.4']
    delivery_list = ['base'] * len(product_list)
    # year_list = [None] * len(product_list)
    year_list = [2024] * len(product_list)      
        
    country_df = efut.fwd_df(sD=(date-timedelta(days=2)),
                           eD=date,
                           product_list=product_list,
                           delivery_list=delivery_list,
                           year_list=year_list)
    
    df = country_df.iloc[[-1]].copy()
    nan_columns_mask = df.isnull().any()
    nan_columns_indices = [df.columns.get_loc(col) for col in nan_columns_mask[nan_columns_mask].index.tolist()]
    selected_elements = [product_list[i] for i in nan_columns_indices if i < len(product_list)]
    selected_columns = [df.columns[i] for i in nan_columns_indices if i < df.shape[1]]
    
    for prod, col in zip(selected_elements, selected_columns):
        prod_type, tenor = prod.split('.')
        settle_start = datetime(2024,int(tenor),1)
        settle_end = settle_start + relativedelta(months=1) - timedelta(days=1)
        db_reader = Database()
        df_spot = db_reader.getSpotPriceData(listOfMarkets=[country],
                                             _from=settle_start.strftime('%Y-%m-%d'),
                                             _to=settle_end.strftime('%Y-%m-%d'))
        df[col][0] = df_spot.mean()[0]

        
    f_dict[country] = []
    f_dict2[country] = country_df.iloc[[-1]]
    for product, col in zip(product_list, country_df.columns):
        if '.' in product:
            product = product.replace('.', '_')
        f_dict[country].append(forward(country,
                                   df[col][0],
                                   start_date(datetime(2023,12,21), product),
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
    


#Hedged positions dict
positions = {}
for country in ['de', 'fr', 'cz', 'hu', 'at']:
    positions[country] = {}
    
positions['de'] = {'M': {'base': {datetime(2024,1,1):[[1, 86.81],
                                                      [-1, 86.06],
                                                      [-1, 86.11]],
                                   datetime(2024,2,1): [[-1, 96.6],
                                                        [-1, 97.1],
                                                        [1, 89.92],
                                                         [1, 81.5],
                                                         [-1, 82.15],
                                                         [1, 75.4],
                                                         [-1, 74.78],
                                                         [-1, 74.19],
                                                         [1, 67.6],
                                                         [-1, 67.82]],
                                   datetime(2024,3,1): [[-1, 86.56],
                                                        [-1, 68.7],
                                                        [-1, 68.15],
                                                        [-1, 67.03],
                                                        [-1, 63.23],
                                                        [1, 60.7],
                                                        [1, 60.84],
                                                        [-1, 55.33],
                                                        [1, 55.37]],
                                   datetime(2024,4,1): [[-1, 51.78],
                                                        [1, 55.65]],
                                   datetime(2024,5,1): [[-1, 53.19],
                                                        [-1, 50.77],
                                                        [-1, 56.25],
                                                        [1, 56.93]],
                                   datetime(2024,6,1): [[-1, 56.41],
                                                        [1, 63.74]],
                                   datetime(2024,10,1): [[-1, 83.5]]}},
                   'Q': {'base': {datetime(2024,1,1): [[1, 88.6],
                                                       [1, 87.44],
                                                       [1, 82.31]],
                                 datetime(2024,4,1): [[-1, 74.45],
                                                      [-1, 76.2],
                                                       [-1, 81.08],
                                                        [1, 78.65],
                                                         [-1, 72.89],
                                                         [1, 63.6],
                                                         [1, 57.05],
                                                         [-1, 52.38],
                                                         [-1, 52.35],
                                                         [1, 53.3],
                                                         [-1, 55.71]],
                                 datetime(2024,7,1): [[-1, 92.35],
                                                      [-1, 90.25],
                                                       [1, 89.4],
                                                       [-1, 89.5],
                                                       [-1, 81.77],
                                                       [-1, 60.91],
                                                       [1, 68.25],
                                                       [-1, 66.91],
                                                       [1, 63.6],
                                                       [1, 71.1],
                                                       [-1, 86.25]],
                                 datetime(2024,10,1): [[1, 105.5],
                                                       [1, 102.44],
                                                        [1, 103.7],
                                                        [1, 87.65],
                                                        [-1, 73.75],
                                                        [1, 83.3],
                                                        [1, 86.19],
                                                        [-1, 81.4],
                                                        [-1, 80.45],
                                                        [-1, 82.98],
                                                        [1, 80.65],
                                                        [1, 98.07],
                                                        [-1, 95.4],
                                                        [-1, 97.9],
                                                        [-1, 103.0],
                                                        [-1, 94.18]]}},
                   'Y': {'base': {datetime(2024,1,1): [[1, 107.95],
                                                      [1, 109],
                                                      [1, 104.85],
                                                      [1,104.75],
                                                      [-1, 101.6]]}}}
positions['cz'] = {'M': {'base': {datetime(2024,1,1): [[-1, 91.81]],
                                  datetime(2024,2,1): [[-1, 85.25]]}},
                   'Q': {'base': {datetime(2024,1,1): [[-1, 93.75]],
                                  datetime(2024,4,1): [[-1, 81.25],
                                                       [-1, 66.1],
                                                       [-1, 56.8]],
                                  datetime(2024,7,1): [[-1, 65.5]],
                                  datetime(2024,10,1): [[-1, 84.8]]}},
                   'Y': {'base': {datetime(2024,1,1): [[1, 105.4]]}}}

positions['fr'] = {'M': {'base': {datetime(2024,1,1): [[1, 84.11],
                                                       [1, 84.06]],
                                  datetime(2024,2,1): [[1, 96.5],
                                                       [1, 80],
                                                       [1, 73.48],
                                                       [1, 66.12]],
                                  datetime(2024,3,1): [[1, 85.81],
                                                       [1, 66.9],
                                                       [1, 66.45],
                                                       [1, 64.53],
                                                       [1, 59.23],
                                                       [-1, 57.7],
                                                       [-1, 58.94],
                                                       [1, 51.83],
                                                       [-1, 52.87]],
                                  datetime(2024,4,1): [[1, 47.53],
                                                       [-1, 40.15]],
                                  datetime(2024,5,1): [[1, 45.69],
                                                       [-1, 24.44]],
                                  datetime(2024,6,1): [[-1, 39.99]],
                                  datetime(2024,10,1): [[1, 67.5]]}},
                   'Q': {'base': {datetime(2024,4,1): [[1, 70],
                                                       [1, 71.6],
                                                        [1, 75.58],
                                                        [1, 67.49],
                                                        [1, 46.35]],
                                 datetime(2024,7,1): [[1, 87.75],
                                                      [1, 84.95],
                                                       [1, 83],
                                                       [1, 75.97],
                                                       [1, 56.66],
                                                       [-1, 62.9],
                                                       [1, 56.41],
                                                       [-1, 59.1]],
                                 datetime(2024,10,1): [[-1, 110.9],
                                                       [-1, 91.8],
                                                       [1, 76.75],
                                                       [-1, 88.1],
                                                       [-1, 96.44],
                                                       [1, 88.4],
                                                       [1, 84.95],
                                                       [1, 84.98],
                                                       [-1, 93.07],
                                                       [1, 89.9],
                                                       [1, 90.9],
                                                       [1, 100.0],
                                                       [1, 91.18]]}},
                   'Y': {'base': {datetime(2024,1,1): [[-1, 113.55]]}}}
positions['hu'] = {'M': {'base': {datetime(2024,2,1): [[1, 103.6],
                                                       [-1, 96.92],
                                                       [-1, 83.5],
                                                       [1, 81.94]]}},
                     'Q': {'base': {datetime(2024,1,1): [[-1, 98.14]],
                                    datetime(2024,4,1): [[-1, 63.05],
                                                         [1, 57.43]],
                                    datetime(2024,7,1): [[-1, 99.3],
                                                         [1, 91.25]],
                                    datetime(2024,10,1): [[-1, 112.44]]}},
                    'Y': {'base': {datetime(2024,1,1): [[-1, 115.45]]}}}
positions['at'] = {'M': {'base': {datetime(2024,2,1): [[-1, 72]],
                                  datetime(2024,5,1): [[1, 50.27],
                                                       [1, 53.25]],
                                  datetime(2024,6,1): [[1, 55.41]]}},
                    'Q': {'base': {datetime(2024,1,1): [[-1, 89.51]],
                                   datetime(2024,4,1): [[1, 56.91]],
                                  datetime(2024,10,1): [[-1, 110.65]]}},
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

# Back up


fw_quarts_dict = {}
for key, series in fw_curve_dict.items():
    fw_quarts_dict[key] = series.resample('Q').mean()

fw_months_dict = {}
for key, series in fw_curve_dict.items():
    fw_months_dict[key] = series.resample('M').mean()
    

spreads_q = pd.DataFrame()
for spread in ['de_hu', 'de_cz', 'de_at', 'de_fr']:
    c1 = spread.split('_')[0]
    c2 = spread.split('_')[1]
    c1_df = fw_quarts_dict[c1]
    c2_df = fw_quarts_dict[c2]
    spread_df = c1_df - c2_df
    spreads_q[spread] = spread_df
    
spreads_m = pd.DataFrame()
for spread in ['de_hu', 'de_cz', 'de_at', 'de_fr']:
    c1 = spread.split('_')[0]
    c2 = spread.split('_')[1]
    c1_df = fw_months_dict[c1]
    c2_df = fw_months_dict[c2]
    spread_df = c1_df - c2_df
    spreads_m[spread] = spread_df

date_range_start = pd.date_range(start='20240101', end='20241231', freq='MS')
date_range_end = pd.date_range(start='20240101', end='20241231', freq='ME')
price_pos_dict = {}
for market in ['de', 'fr', 'cz', 'hu', 'at']:
    price_long, vol_long, price_short, vol_short = [],[],[],[]
    
    for start in date_range_start:
        month = start.month
        long_price, long_vol, short_price, short_vol = get_price_vol(positions,market,
                                                                      month)
        price_long.append(long_price)
        vol_long.append(long_vol)
        price_short.append(short_price)
        vol_short.append(short_vol)
        
    df = pd.DataFrame([price_long, vol_long, price_short, vol_short],
                      columns=date_range_start,
                      index=['long_price', 'long_vol',
                              'short_price', 'short_vol']).T
    price_pos_dict[market] = df
        
        
        
        

# posHedgeClass = PositionManagerHedge(hedgeContr, 0)
# posCapaClass.sum_(posHedgeClass, fw_curve_dict, 'MS').round(2)
