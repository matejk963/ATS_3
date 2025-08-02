# -*- coding: utf-8 -*-
"""
Created on Mon Nov 13 10:27:56 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import datetime as dt

import sys
sys.path.append('X:\\BorderSpread')
sys.path.append('X:\\Curve')
sys.path.append('X:\\Loaders')
sys.path.append('X:\\Utilities')
from portfolio_sim import capaStratSim
from capacity_contract_class import CapacityContr
from capacity_class import ImplicitCapacity
from border_class import DataBorderClass
from EikonSpot_class import EikonSpot
from loader_web import JaoLoader
from Database.DB_reader import Database
from BorderSpread.Capa_functions import save_dfs_to_excel as DF2E


horizon = 'Y'
bT = datetime(2022, 1, 1)
eT = datetime(2024, 1, 1)
date_range = pd.date_range(bT, eT, freq=horizon + 'S')[:-1]

# Historical data
start_d = datetime(2019, 1, 1)
end_d = datetime(2023, 10, 1) - timedelta(hours=1)

### Capacity ###
border_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
               'de_nl', 'nl_de', 'be_nl', 'nl_be',
               'be_fr', 'fr_be',
               'de_at', 'at_de', 'at_hu', 'hu_at',
               'at_cz', 'cz_at', 'cz_de', 'de_cz']

border_type = ['implicit'] * len(border_list)
delivery_ = ['base']

bs_class = DataBorderClass(border_list, border_type, start_d, end_d)
bs_class.load_data()

data_train = dict()
for del_ in delivery_:
    data_train[del_] = bs_class.aggregate_data('M', delivery=del_)
    
    
capa_list = []
for b in border_list:
    capacity = ImplicitCapacity([b], delivery_)
    capa_list.append(capacity)
    
# Strategy class
capa_strat = capaStratSim()
[capa_strat.add_contract(CapacityContr(c, 0, 'base', bT, 'Y')) for c in capa_list]

### Load data for spot & futures ###
start = bT - relativedelta(months=2)
mkt_list_s = capa_strat.market_list
dict_df_fwd = {}
df_spot = pd.DataFrame()
spot_sD = datetime(start.year, start.month, 1)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                     _from=spot_sD.strftime('%Y-%m-%d'),
                                     _to=eT.strftime('%Y-%m-%d'))

tenor_list = ['M_1', 'M_2', 'M_3', 'M_4', 'Q_2', 'Q_3', 'Q_4']
tenor_list = ['M_0', 'Y_1']
tenor_label_list = ['tenor_'+str(a) for a in range(len(tenor_list))]
for m in mkt_list_s:
    
    eikon_spot = EikonSpot( m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    # # df_aux = eikon_spot.prices_df()
    # df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    dict_df_fwd[m] = eikon_spot.fwd_df_rel(start, eT, tenor_list, ['base'] * len(tenor_list))
    # dict_df_fwd[m][tenor_label_list] = tenor_list

df_spot = df_spot.reindex(pd.date_range(start, eT - relativedelta(hours=1), freq='H'))
df_spot.fillna(method='ffill', inplace=True)

### Load auctions ###
jao_loader = JaoLoader()
df_auct_dict = jao_loader.auction_loader(border_list, date_range, horizon)

### Backtest ###
reg_list = ['capa_settl', 'spread', 'ext_fair', 'ext_auc']
pnl_dict_unhedged, reg_dict = capa_strat.backtest_all(date_range, df_spot, dict_df_fwd, df_auct_dict,
                                              data_train, fix_delta=False, delta_factor=0,
                                              freq='YS', lookback=12, reg_list=reg_list)
pnl_dict_hedged, reg_dict = capa_strat.backtest_all(date_range, df_spot, dict_df_fwd, df_auct_dict,
                                              data_train, fix_delta=False, delta_factor=1,
                                              freq='YS', lookback=12, reg_list=reg_list)

# pnl_dict, reg_dict = capa_strat.backtest_rlt(date_range, df_spot, dict_df_fwd, df_auct_dict,
#                                              data_train, fix_delta=False, delta_factor=1,
#                                              val_factor=2,
#                                              freq='MS', lookback=12, reg_list=reg_list)

pnl_df_unhedged = pd.DataFrame({k: v['tot'] for k, v in pnl_dict_unhedged.items()})
pnl_df_hedged = pd.DataFrame({k: v['tot'] for k, v in pnl_dict_hedged.items()})

            
DF2E(reg_dict, r'S:\Capa\Backtest\reg_dict_yearly.xlsx')
DF2E(pnl_dict_hedged, r'S:\Capa\Backtest\pnl_dict_hedged_yearly.xlsx')
DF2E(pnl_dict_unhedged, r'S:\Capa\Backtest\pnl_dict_unhedged_yearly.xlsx')



