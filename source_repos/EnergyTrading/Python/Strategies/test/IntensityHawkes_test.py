# -*- coding: utf-8 -*-
"""
Created on Tue Jan 30 12:57:40 2024

@author: krajcovic
"""


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import datetime as dt
from datetime import datetime, timedelta

from Strategies.HwksInt_retraining_class import MultiTradeIntensity as TI
from Database.TPData import TPDataAssembly as TDA

# assembler = TDA(source='database')
# params_dict = {}

# params_dict['tenor_list'] = ['m']
# params_dict['tn1_list'] = [1]
# params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
# params_dict['tn2_list'] = []
# params_dict['prod'] = 'base'
# params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
# params_dict['start_date'] = datetime(2023, 10, 1)
# params_dict['end_date'] = datetime(2024, 1, 28)
# params_dict['ns'] = 2

# # Fetch trades and best orders for the curve
# assembler = TDA(source='trayport', user='matej')
# # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
# trades_dict = assembler.get_data(params_dict, target_data='trades')
# assembler.set_data_source('database')
# ba_dict = assembler.get_data(params_dict, target_data='best_orders')

# assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"

# for key in trades_dict.keys():
#     ti_inst = TI(trades_dict[key], ba_dict[key])
#     ti_inst.set_conditions()
#     # train_dict, test_dict = ti_inst.create_train_test_dict(train_size=0.8)

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\ba_test.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\trades_test.csv',
                    parse_dates=['datetime']).set_index('datetime')

ti_inst = TI(trades, ba, ['dem1'])

ti_inst.calculate_intensities()

# ti_inst.prepare_data()
# ti_inst.set_conditions()
# ti_inst.create_train_test_dict()
# ti_inst.estimate_params()

# params_dict = ti_inst.params_dict

# ask_params = []
# bid_params = []
# for date, date_dict in params_dict.items():
#     for prod, prod_dict in date_dict.items():
#         for ba, ba_list in prod_dict.items():
#             if ba in ['ask_params']:
#                 ask_params.append(ba_list)
#             else:
#                 bid_params.append(ba_list)
# bid_df = pd.DataFrame(bid_params, columns=['mu', 'alpha', 'beta'])
# ask_df = pd.DataFrame(ask_params, columns=['mu', 'alpha', 'beta'])

# for column in ask_df:
#     plt.figure()  # Creates a new figure
#     ask_df[column].plot(kind='density')  # Creates a density plot
#     plt.title(f'Density Plot of {column}')
#     plt.xlabel(column)
#     plt.ylabel('Density')
#     plt.grid(True)  # Turn on the grid for better readability
#     plt.show()


# ti_inst.set_train_size(0.75)
# ti_inst.estimate_params()
# fut_periods_dict = {}
# fut_periods_dict['mean'] = {}
# fut_periods_dict['count'] = {}
# for t in [5, 10, 20]:

    
#     ti_inst.calculate_intensities()
    
#     train_dict = ti_inst.train_dict
#     test_dict = ti_inst.test_dict
    
#     ti_inst.get_bull_bear_move(t=t)
    
    
    
#     stats_dict = {}
#     for stat in ['mean', 'count']:
#         stats_dict[stat] = pd.DataFrame()
#         for date, aux_dict in test_dict.items():
#             aux = aux_dict['trades']
#             aux['int_bid_round'] = round(aux['int_bid'],0)
#             aux['int_ask_round'] = round(aux['int_ask'],0)
#             if stat in ['mean']:
#                 bid_sum = aux[['int_bid_round', 'bull_bear_result']].groupby(['int_bid_round']).mean()
#                 ask_sum = aux[['int_ask_round', 'bull_bear_result']].groupby(['int_ask_round']).mean()
#             elif stat in ['count']:
#                 bid_sum = aux[['int_bid_round', 'bull_bear_result']].groupby(['int_bid_round']).count()
#                 ask_sum = aux[['int_ask_round', 'bull_bear_result']].groupby(['int_ask_round']).count()
#             aux_sum = pd.concat([bid_sum, ask_sum], axis=1)
#             if stats_dict[stat].empty:
#                 stats_dict[stat] = aux_sum.copy()
#             else:
#                 stats_dict[stat] = pd.concat([stats_dict[stat], aux_sum])
            
#     fut_periods_dict['mean'][t] = stats_dict['mean'].reset_index().groupby(['index']).mean()
#     fut_periods_dict['count'][t] = stats_dict['count'].reset_index().groupby(['index']).sum()
    
    
    
# for t in [5,10,20]:
#     fut_periods_dict['mean'][t].plot()

# agg_ret = []
# for date, aux_dict in test_dict.items():
#     trades = aux_dict['trades']
#     trades.dropna(inplace=True)
#     trades = trades[['price']].copy()
#     agg_ret.append(round(((trades/trades.shift(1)).mean()[0]-1)*len(trades),3))
    

    
    
