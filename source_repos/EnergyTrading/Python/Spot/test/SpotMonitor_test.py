# -*- coding: utf-8 -*-
"""
Created on Wed Jan 17 14:41:55 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import RldMonitor as RM
from sklearn.linear_model import LinearRegression

from Database.TPData import TPDataAssembly as TDA
from Strategies.Intensity_class import TradeIntensity as TI

import statsmodels.api as sm



sD = datetime(2023,1,1)
eD = datetime(2024,2,20)

params_dict = {}


params_dict['market_list'] = ['at', 'be', 'cz', 'de', 'dkw', 'dke', 'fr', 'hu', 'nl', 'sk']
# params_dict['market_list'] = ['de', 'gas']
params_dict['product_list'] = ['spot'] * len(params_dict['market_list'])
params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = datetime(2024, 1, 1)
params_dict['eD'] = datetime(2024, 3, 31)
params_dict['ns'] = 2


settle_mon = SM(params_dict)

spot_data = settle_mon.get_spot_data_raw()

# mon_inst = RM()
# mon_inst.set_date_range(sD, eD)

# raw_data = mon_inst.get_raw_data(market='fr', source='local')


# test = mon_inst.process_data(raw_data)

# da_data = mon_inst.get_da_data(test)


# mon_inst.set_da_lookback(14)

# stats_h = mon_inst.assemble_stat(test, stat_type='hist')
# stats_f = mon_inst.assemble_stat(test, stat_type='fcst')
# stats = stats_h.merge(stats_f, left_index=True, right_index=True, suffixes=('_h', '_f'),
#                       how='right')

# # stats['mean_p'] = pd.qcut(stats['mean_h'],5,labels=False)
# # stats['std_p'] = pd.qcut(stats['std_h'],5,labels=False)
# # stats['skew_p'] = pd.qcut(stats['skew_h'],5,labels=False)

# mon_inst.plot_stats(test)



# params_dict = {}

# params_dict['tenor_list'] = ['w', 'w', 'w']
# params_dict['tn1_list'] = [1,2,3]
# params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
# params_dict['tn2_list'] = []
# params_dict['prod'] = 'base'
# params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
# params_dict['start_date'] = datetime(2023, 10, 1)
# params_dict['end_date'] = datetime(2024, 1, 24)
# params_dict['ns'] = 2

# # Fetch trades and best orders for the curve
# assembler = TDA(source='trayport', user='matej')
# # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
# trades_dict = assembler.get_data(params_dict, target_data='trades')




# # Go key by key(product by product) in dictionaries and process through Intensity Class
# # together to get proper trade side
# # Concat the porcessed products to one df
# data = pd.DataFrame()
# for key in trades_dict.keys():
#     trades_aux = trades_dict[key].loc[trades_dict[key]['broker_id']==14].copy()
    
#     if data.empty:
#         data = trades_aux.copy()
#     else:
#         data = pd.concat([data, trades_aux])


# def compute_daily_vwap(df):
#     # Convert the 'datetime' column to datetime objects and set as index
#     # df['datetime'] = pd.to_datetime(df['datetime'])
#     # df.set_index('datetime', inplace=True)

#     # Calculate daily VWAP
#     vwap = df.groupby(df.index.date).apply(lambda x: (x['price'] * x['volume']).sum() / x['volume'].sum())
#     vwap.index = pd.to_datetime(vwap.index)
#     return vwap

# import plotly.graph_objects as go
# import pandas as pd

# def plot_vwap_with_slider_plotly(vwap_dict):
#     # Create a list of unique dates across all VWAPs, ensuring they are pandas Timestamps
#     all_dates = sorted(set().union(*(pd.to_datetime(vwap.index) for vwap in vwap_dict.values())))
#     all_dates_str = [date.strftime('%Y-%m-%d') for date in all_dates]

#     # Create traces for each product for each date
#     traces = []
#     for date in all_dates:
#         for product, vwap in vwap_dict.items():
#             vwap_value = vwap.get(date, None)
#             if vwap_value is not None:
#                 traces.append(go.Scatter(
#                     x=[product],
#                     y=[vwap_value],
#                     mode='markers+text',  # Add text mode for labels
#                     text=[f"{vwap_value:.2f}"],  # Text label showing VWAP value
#                     textposition='top center',
#                     marker=dict(size=10),
#                     name=f"{product} ({date.strftime('%Y-%m-%d')})",
#                     visible=False  # Start with all traces hidden
#                 ))

#     # Create the figure with initial data
#     fig = go.Figure(data=traces)

#     # Add slider steps
#     steps = []
#     for date in all_dates:
#         step = dict(
#             method='update',
#             args=[{'visible': [False] * len(traces)}],  # Start by hiding all traces
#             label=date.strftime('%Y-%m-%d')
#         )
#         # Show only the traces that correspond to this date
#         for j, trace in enumerate(traces):
#             if trace['name'].endswith(f"({date.strftime('%Y-%m-%d')})"):
#                 step['args'][0]['visible'][j] = True
#         steps.append(step)

#     # Create and add slider
#     sliders = [dict(
#         active=0,
#         currentvalue={"prefix": "Date: "},
#         pad={"t": 50},
#         steps=steps
#     )]

#     fig.update_layout(
#         sliders=sliders,
#         xaxis_title="Product",
#         yaxis_title="VWAP",
#         title="VWAPs for Different Products Over Time"
#     )

#     # Initially show the first set of traces (for the first date)
#     for j, trace in enumerate(traces):
#         if trace['name'].endswith(f"({all_dates[0].strftime('%Y-%m-%d')})"):
#             fig.data[j].visible = True

#     fig.show(renderer="browser")

    
    
# vwap_dict = {product: compute_daily_vwap(df) for product, df in trades_dict.items()}

# plot_vwap_with_slider_plotly(vwap_dict)

