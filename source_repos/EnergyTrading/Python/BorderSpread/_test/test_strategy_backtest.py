# -*- coding: utf-8 -*-
"""
Created on Wed Aug  2 16:57:18 2023

@author: Marek
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


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


horizon = 'M'
bT = datetime(2021, 1, 1)
eT = datetime(2023, 10, 1)
date_range = pd.date_range(bT, eT, freq=horizon + 'S')[:-1]

# Historical data
start_d = datetime(2019, 1, 1)
end_d = datetime(2023, 10, 1) - timedelta(hours=1)

### Capacity ###
border_list = ['de_fr', 'fr_de', 'dke_de', 'de_dke',
                'at_de', 'de_at', 'be_de', 'de_be',
                'be_fr', 'fr_be', 'be_nl', 'nl_be',
                'de_nl', 'nl_de', 'hu_ro', 'ro_hu',
                'de_cz', 'cz_de']

border_list = ['dkw_de', 'de_dkw', 'dkw_nl', 'nl_dkw',
                'at_cz', 'cz_at', 'at_hu', 'hu_at',
                'at_si', 'si_at', 'cz_de', 'de_cz',
                'cz_sk', 'sk_cz',
                'sk_hu', 'hu_sk', 'dkw_dke', 'dke_dkw']



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
[capa_strat.add_contract(CapacityContr(c, 0, 'base', bT, horizon)) for c in capa_list]

### Load data for spot & futures ###
start = bT - relativedelta(months=1)
mkt_list_s = capa_strat.market_list
dict_df_fwd = {}
df_spot = pd.DataFrame()
spot_sD = datetime(start.year, start.month, 1)
db_reader = Database()
df_spot = db_reader.getSpotPriceData(listOfMarkets=mkt_list_s,
                                     _from=spot_sD.strftime('%Y-%m-%d'),
                                     _to=eT.strftime('%Y-%m-%d'))
for m in mkt_list_s:
    
    eikon_spot = EikonSpot( m, spot_sD.strftime('%Y%m%d'), eT.strftime('%Y%m%d'))
    # # df_aux = eikon_spot.prices_df()
    # df_spot = pd.concat([df_spot, df_aux], axis=1)
    # Forwards
    dict_df_fwd[m] = eikon_spot.fwd_df_rel(start, eT, ['M_0', 'M_1'], ['base'] * 2)

df_spot = df_spot.reindex(pd.date_range(start, eT - relativedelta(hours=1), freq='H'))
df_spot.fillna(method='ffill', inplace=True)

### Load auctions ###
jao_loader = JaoLoader()
df_auct_dict = jao_loader.auction_loader(border_list, date_range, horizon)

### Backtest ###
reg_list = ['capa_settl', 'spread', 'ext_fair', 'ext_auc']
pnl_dict, reg_dict = capa_strat.backtest_all(date_range, df_spot, dict_df_fwd, df_auct_dict,
                                              data_train, fix_delta=False, delta_factor=0,
                                              freq='MS', lookback=12, reg_list=reg_list)

# pnl_dict, reg_dict = capa_strat.backtest_rlt(date_range, df_spot, dict_df_fwd, df_auct_dict,
#                                              data_train, fix_delta=False, delta_factor=1,
#                                              val_factor=2,
#                                              freq='MS', lookback=12, reg_list=reg_list)

pnl_df = pd.DataFrame({k: v['tot'] for k, v in pnl_dict.items()})
