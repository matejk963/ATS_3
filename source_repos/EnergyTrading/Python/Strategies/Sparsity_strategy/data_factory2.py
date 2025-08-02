# -*- coding: utf-8 -*-
"""
Created on Thu May 30 12:52:41 2024

@author: scasny
"""

from datetime import datetime, time
import pandas as pd
import numpy as np

from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
from Strategies.Sparse_momentum.ob_attributes import diff, unify_time_pd
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Database.TPData import TPData, TPDataDa


def product_dates(dates, t, tn, n_s):
    # Product dates
    pd_list = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                dates.shift(tn, freq='YS') if t == 'dec' else
                (dates + n_s * dates.freq).shift(tn, freq='AS-Apr') if t in ['sum'] else
                (dates + n_s * dates.freq).shift(tn, freq='AS-Oct') if t in ['win'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')]
    return pd_list

n_s = 2
# mkt_list = ['de', 'de', 'de']
primary_mkt = {
    'mkt': 'de',
    'tenor': 'm',
    'tn1': 1
}
secondary_mkts = [
    {'mkt': 'de', 'tenor': 'q', 'tn1': 1},
    {'mkt': 'de', 'tenor': 'y', 'tn1': 1},
    {'mkt': 'ttf', 'tenor': 'm', 'tn1': 1}
]


prod = 'base'
venue_list = ['eex']
# Order book features variables
features_list = ['ba_volrat', 'mid_priceW', 'sparsity', 'p_movement']
depth_list = [0.1, 0.15, 0.2, 0.3, 0.5, 1.0]
tick = 0.01
tick_val = 200
cls_margin = 0.10
obAtt = OB_attributes(features_list)
#   -   -   - 
start_date = datetime(2023, 11, 1)
end_date = datetime(2023, 11, 1)
# end_date = datetime(2024, 5, 17)    
dates = pd.date_range(start_date, end_date, freq='B')

primary_mkt['pd'] = product_dates(dates, primary_mkt['tenor'], primary_mkt['tn1'], n_s)
_ = [sec_m.update({'pd': product_dates(dates, sec_m['tenor'], sec_m['tn1'], n_s)}) for sec_m in secondary_mkts]


start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)

data_class = TPDataDa()
df_data = pd.DataFrame()

primary_trades = pd.DataFrame()

for ds, pd1 in zip(dates, *primary_mkt['pd']):
    try:
        bT = datetime.combine(ds, start_time)
        eT = datetime.combine(ds, end_time)
        ob_class = OrderBookSnaps(verbose=True)

        trades = data_class.get_trades(primary_mkt['mkt'], primary_mkt['tenor'], venue_list, pd1, bT, eT, prod)
        df_ord_data = data_class.get_orders_data(primary_mkt['mkt'], primary_mkt['tenor'], venue_list, pd1,
                                            bT, eT, prod, None)
        ob_class.import_from_tp(df_ord_data)

        data_dict = obAtt.prepare_ob_data(ob_class.LoB_dict, depth_list)
        
        idx, csum = obAtt.calc_tick_index(data_dict, None, None, 1, tick=tick)
        class_ser = obAtt.prepare_class_data(data_dict, csum, idx,
                                                tick_val, cls_margin)
        # reg_df = obAtt.prepare_reg_data_mkt(data_dict, ob_class.time_list, idx, [3, 5, 10, 20], [0.15, 0.25, 0.5])
        df_current = pd.DataFrame(data_dict).set_index('timestamp')
        df_current['y'] = class_ser['class']
        df_current.reset_index(inplace=True)
        
        if df_data.empty:
            df_data = df_current.copy()
            primary_trades = trades.copy()
        else:
            df_data = pd.concat([df_data, df_current])
            primary_trades = pd.concat([primary_trades, trades])

    except Exception as e:
        print(e)
        pass
    
        for trade in trades.reset_index().to_dict(orient='records'):
            ts = trade['datetime']
            index = get_index_for_ts(pd.Series(ob_class.time_list), ts)
            df_current.loc[index, 'trd_price'] = trade['price']
            df_current.loc[index, 'trd_vol'] = trade['volume']
            df_current.loc[index, 'last_hour_vol'] = df_current[(df_current['timestamp'] > (ts - pd.Timedelta(hours=1))) & (df_current['timestamp'] < ts)]['trd_vol'].sum()
            df_current.loc[index, 'trd_side'] = 0 if abs(df_current.loc[index, 'b_price'] - trade['price']) <  abs(df_current.loc[index, 'a_price'] - trade['price']) else 1
        
        df_current['last_trd_p'] = df_current['trd_price']
        df_current['last_trd_p'].ffill(inplace=True)
        df_current['bid_t1'] = df_current['b_price'].shift(-1) == df_current['b_price']
        df_current['ask_t1'] = df_current['a_price'].shift(-1) == df_current['a_price']
        
sec_dict = {}
for mkt_dict in secondary_mkts:
    current_df = pd.DataFrame()
    for ds, pd1 in zip(dates, *mkt_dict['pd']):
        try:
            bT = datetime.combine(ds, start_time)
            eT = datetime.combine(ds, end_time)
            
            trades = data_class.get_trades(mkt_dict['mkt'], mkt_dict['tenor'], venue_list, pd1, bT, eT, prod)
            if current_df.empty:
                current_df = trades
            else:
                current_df = pd.concat([current_df, trades])
        except Exception as e:
            print(e)
            pass
    sec_dict[f"{mkt_dict['mkt']}_{mkt_dict['tenor']}"] = current_df

df_data = df_data.set_index('timestamp').reset_index()
for sec_mkt, df in sec_dict.items():
    col_name = f"diff_{sec_mkt}"
    df = df[~df.index.duplicated()]
    diff_series = diff(df['price'], 5, True)
    for ts, price in diff_series.to_dict().items():
        index = get_index_for_ts(df_data['timestamp'], ts)
        df_data.loc[index, col_name] = price
    df_data[col_name].ffill(inplace=True)

df_data['hour'] = df_data['timestamp'].dt.hour
df_data['last_trade_margin'] = df_data['last_trd_p'] - df_data['mid_price']
