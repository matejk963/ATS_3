# -*- coding: utf-8 -*-
"""
Created on Tue Jun 11 11:20:44 2024

@author: Marek
"""

from datetime import datetime, time
import datetime as dt
from Database.TPData import TPData, TPDataDa
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import Attributes
from Strategies.IntensityHawkes_strategy.model_class_update import HawkesIntensity as HI
import pandas as pd
import numpy as np

l_path = '//192.168.10.91/data/Data/orderbooks/base/'


n_s = 2
mkt_list = ['de', 'de', 'de', 'ttf']
tenor_list = ['m', 'q', 'y', 'm']
tn1_list = [1, 1, 1, 1]
tn2_list = []
prod = 'base'
venue_list = ['eex'] * len(mkt_list)
start_date = datetime(2024, 6, 20)
end_date = datetime(2024, 7, 3)

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

dates = pd.date_range(start_date, end_date, freq='B')

spread_class = SpreadSingle(mkt_list, tenor_list, tn1_list, tn2_list, venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)

name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]

gran = None

agg_dict = {'vwp': 'sum', 'volume': 'sum', 'action': 'median',
            'broker_id': 'median', 'count': 'sum'}

pd_tr = pd.DataFrame([])
data_class_tr = TPDataDa()
for k, ds in enumerate(dates):
    tr_dicts = {k: {} for k in range(len(name_list))}
    bT = datetime.combine(ds, start_time)
    eT = datetime.combine(ds, end_time)
    pd1_aux = [None if p is None else p[k] for p in product_date1]
    pd2_aux = [None if p is None else p[k] for p in product_date2]
    for i, (m, t, n, pd1, pd2) in enumerate(zip(mkt_list, tenor_list, tn_list,
                                                pd1_aux, pd2_aux)):
        data_class_tr.create_connection('OracleSQL')
        try:
            df_tr = data_class_tr.get_trades(m, t, venue_list, pd1, bT, eT, prod)
            df_tr['count'] = 1
            df_tr['vwp'] = df_tr['price'] * df_tr['volume']
            df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
            df_tr['vwp'] = df_tr['vwp'] / df_tr['volume']
            tr_dicts[i] = df_tr
        except:
            continue
        
    ts = Attributes.unify_timestamp(tr_dicts, gran, None)
    
    pd_tr = pd.concat([pd_tr, tr_dicts[0].reindex(ts)])
    
    
    
train_data = pd_tr[pd_tr.index.date<dt.date(2024,5,10)].copy()
test_data = pd_tr[pd_tr.index.date==dt.date(2024,5,10)].copy()

trades_train = train_data.loc[~train_data['vwp'].isna()].copy()
train_ba = train_data.loc[train_data['vwp'].isna()].copy()

train_data.columns = [a + '_dem1' for a in train_data.columns]

pd_tr_adj = pd_tr.copy()
pd_tr_adj.columns = [a + '_dem1' for a in pd_tr_adj.columns]

int_inst = HI(pd_tr_adj, ['dem1'])

int_inst.estimate_params()

bid_event_times = test_data.loc[(test_data['action']==-1)].index.copy()
ask_event_times = test_data.loc[(test_data['action']==1)].index.copy()

int_inst.update_event_times(bid_event_times, 'bid')
int_inst.update_event_times(ask_event_times, 'ask')

int_bid_list = []
int_ask_list = []
for i in test_data.index:
    mu_bid, alpha_bid, beta_bid = int_inst.params_dict[dt.datetime(2024,5,10)]['dem1']['bid_params']
    mu_ask, alpha_ask, beta_ask = int_inst.params_dict[dt.datetime(2024,5,10)]['dem1']['ask_params']
    if i < test_data.dropna(subset=['action']).index[0]:
        int_bid_list.append(np.nan)
        int_ask_list.append(np.nan)
        continue
    else:
        int_bid_list.append(int_inst.hawkes_intensity(i, mu_bid, alpha_bid, beta_bid, 'bid'))
        int_ask_list.append(int_inst.hawkes_intensity(i, mu_ask, alpha_ask, beta_ask, 'ask'))
test_data['bid_int'] = int_bid_list
test_data['ask_int'] = int_ask_list
        
    






