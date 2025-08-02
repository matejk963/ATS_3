# -*- coding: utf-8 -*-
"""
Created on Fri Oct  4 14:12:45 2024

@author: Marek
"""

from datetime import datetime, time
from Database.TPData import TPData
from SynthSpread.spreadviewer_class import SpreadSingle
import pandas as pd
import matplotlib.pyplot as plt
from Strategies.Arbitrage_strategy.backtest_class import BacktestArb
import scipy.stats as stats


def group_trades(df_tr, agg_dict):
    # Group trades
    df_tr['count'] = 1
    df_tr['price'] *= df_tr['volume']
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
    df_tr['price'] /= df_tr['volume']
    return df_tr.loc[:, ['price', 'volume', 'action', 'broker_id']]


n_s = 2
# mkt_list = ['de', 'de', 'de', 'de', 'de', 'de', 'de', 'de', 'fr', 'fr', 'fr', 'fr']
# tenor_list = ['m', 'm', 'q', 'q', 'q', 'q', 'y', 'y', 'm', 'm', 'q', 'q']
# tn1_list = [1, 2, 1, 2, 3, 4, 1, 2, 1, 2, 1, 2]
mkt_list = ['de']
tenor_list = ['q']
tn1_list = [1]
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 4, 3)
end_date = datetime(2024, 4, 3)

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

data_class = TPData()

is_ob = False
brk_ids = [1441]

backtest_class = BacktestArb()

cols = ['price', 'volume', 'action', 'broker_id']
agg_dict = {'price': 'first', 'volume': 'first', 'action': 'first',
            'broker_id': 'first', 'count': 'first'}

tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
mr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date1):
    df_tr = pd.DataFrame([])
    mrg_ser = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        data_class.create_connection('OracleSQL')
        try:
            df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        except AttributeError:
            continue
        df_tr_all = df_tr_aux.copy()
        df_tr_aux = df_tr_aux.loc[df_tr_aux['own_trades'], cols]
        # Group trades
        df_tr_aux = group_trades(df_tr_aux, agg_dict).between_time(start_time, end_time)
        if df_tr.empty:
            df_tr = df_tr_all
        else:
            df_tr = pd.concat([df_tr, df_tr_all])
        # Orders
        df_ba = None
        try:
            mrg_ser_aux = backtest_class.trd_arb(df_ba, df_tr_aux, brk_ids, side='all')
        except:
            mrg_ser_aux = pd.DataFrame([])
        if mrg_ser.empty:
            mrg_ser = mrg_ser_aux
        else:
            mrg_ser = pd.concat([mrg_ser, mrg_ser_aux])
    tr_data_dict[m + t + str(n)] = df_tr
    mr_data_dict[m + t + str(n)] = mrg_ser


opp_dict = {k: v[v != 0].dropna() for k, v in mr_data_dict.items()}

# cut_date = datetime(2024, 10, 3).date()
# cut_time = 1.5

# cont_dict = {k: list(v.loc[v.index.date < cut_date, 'time_diff'].values) for k, v in opp_dict.items()}
# test_dict = {k: list(v.loc[v.index.date >= cut_date, 'time_diff'].values) for k, v in opp_dict.items()}

# # Test distribution
# out_dict = {}
# for m in opp_dict.keys():
#     test_values = [x for x in test_dict[m] if x < cut_time]
#     control_values = [x for x in cont_dict[m] if x < cut_time]
#     t_stat, p_value = stats.ttest_ind(test_values, control_values, alternative='less', equal_var=False)
#     out_dict[m] = p_value
