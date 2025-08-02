# -*- coding: utf-8 -*-
"""
Created on Fri Sep 20 14:30:21 2024

@author: Marek
"""

from datetime import datetime, time
from Database.TPData import TPData
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
import pandas as pd
import matplotlib.pyplot as plt
from Strategies.Arbitrage_strategy.backtest_class import BacktestArb

l_path = '//192.168.10.91/data/Data/orderbooks/base/'


def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)


def group_trades(df_tr, agg_dict):
    # Group trades
    df_tr['count'] = 1
    df_tr['price'] *= df_tr['volume']
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
    df_tr['price'] /= df_tr['volume']
    return df_tr.loc[:, ['price', 'volume', 'action', 'broker_id']]


n_s = 2
mkt_list = ['de', 'de', 'de', 'de', 'de', 'de', 'de', 'de']
tenor_list = ['m', 'm', 'q', 'q', 'q', 'q', 'y', 'y']
tn1_list = [1, 2, 1, 2, 3, 4, 1, 2]
# mkt_list = ['es', 'it', 'es', 'it', 'es', 'it']
# tenor_list = ['y', 'y', 'q', 'q', 'm', 'm']
# tn1_list = [1, 1, 1, 1, 1, 1]
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 12, 1)
end_date = datetime(2024, 12, 8)

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

is_ob = True
brk_ids = [1441]
agg_dict = {'price': 'first', 'volume': 'first', 'action': 'first',
            'broker_id': 'first', 'count': 'first'}

backtest_class = BacktestArb()


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
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        # Group trades
        df_tr_aux = group_trades(df_tr_aux, agg_dict).between_time(start_time, end_time)
        if df_tr.empty:
            df_tr = df_tr_aux
        else:
            df_tr = pd.concat([df_tr, df_tr_aux])
        # Orders
        if not is_ob:
            data_class.create_connection('PostgreSQL')
            df_ba = data_class.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None)
            try:
                mrg_ser_aux = backtest_class.trd_arb(df_ba, df_tr, brk_ids, side='all')
            except:
                mrg_ser_aux = pd.DataFrame([])
            if mrg_ser.empty:
                mrg_ser = mrg_ser_aux
            else:
                mrg_ser = pd.concat([mrg_ser, mrg_ser_aux])
    if is_ob:
        for p_d, ds in zip(p_dates, dates):
            bT = datetime.combine(ds, start_time)
            eT = datetime.combine(ds, end_time)
            # Orders
            ob_class = OrderBookSnaps(verbose=True)
            LoB, ts = load_ob(m, t, bT, p_d, bT, eT)
            ob_class.update_data(LoB, ts)
            # Get margin
            df_trades = df_tr.loc[df_tr.index.date == ds.date(), :]
            df_ba = backtest_class.prepare_order_data(ob_class)
            try:
                mrg_ser_aux = backtest_class.trd_arb(df_ba, df_trades, brk_ids,
                                                     side='all')
            except:
                continue
            if mrg_ser.empty:
                mrg_ser = mrg_ser_aux
            else:
                mrg_ser = pd.concat([mrg_ser, mrg_ser_aux])
    tr_data_dict[m + t + str(n)] = df_tr
    mr_data_dict[m + t + str(n)] = mrg_ser


sk = mr_data_dict['dey1'][mr_data_dict['dey1'] != 0].dropna()
#sk1 = sk.loc[sk.index.date == datetime(2024, 9, 30).date()]
#print(sk1.groupby(sk1).count())

out_dict = {k: v[v != 0].dropna() for k, v in mr_data_dict.items() if not v.empty}
