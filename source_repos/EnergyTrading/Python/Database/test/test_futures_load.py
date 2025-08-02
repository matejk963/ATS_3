import pandas as pd
import numpy as np
from datetime import datetime, time
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
 
def adjust_trds(df_tr, df_em):
    timestamp = df_tr.index
    ts_new = df_em.index.union(timestamp)
    df_em = df_em.reindex(ts_new).ffill().reindex(timestamp)
    lb = df_em.iloc[:, 0]
    ub = df_em.iloc[:, 2]
    df_tr.loc[df_tr['buy'] > ub, 'buy'] = np.nan
    df_tr.loc[df_tr['sell'] < lb, 'sell'] = np.nan
    return df_tr.dropna(how='all')
 
 
n_s = 0
start_date = datetime(2020, 1, 15)
end_date = datetime(2024, 12, 10)
dates = pd.date_range(start_date, end_date, freq='B')
 
# ---------------Enter secondary market for spread --------------------
 
market = ['fr'] # market area e.g. (de, fr, eua, ttf)
tenor = ['q'] # period e.g. (w, m, q, y) for eua only "dec"
tn1_list = [3] # target period e.g. (the number in m1, m2, q1, q2)
tn2_list = [] # keep blank when not using as a spread
mm_bool = [True] # 1 or 2 depending whether it is a spread
# ---------------------------------------------------------------------
 
brk_list = ['eex']
 
 
start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)
gran = None
gran_s = '1s'
coeff_list = norm_coeff([1], market)
 
add_trades = True
ob_data = False # od 2021 ked false
 
 
spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
data_class = SpreadViewerData()
if ob_data:
    db_class = TPData()
else:
    db_class = TPDataDa()
 
tenors_list = spread_class.tenors_list
if ob_data:
    data_class.load_best_order_otc(market, tenors_list,
                                   spread_class.product_dates(dates, n_s),
                                   db_class,
                                   start_time=start_time, end_time=end_time)
else:
    data_class.load_best_ob_tp(market, tenors_list,
                               spread_class.product_dates(dates, n_s),
                               db_class,
                               start_time=start_time, end_time=end_time)
if add_trades:
    data_class_tr = SpreadViewerData()
    data_class_tr.load_trades_otc(market, tenors_list, db_class,
                                  start_time=start_time, end_time=end_time)
sm_all = pd.DataFrame([])
tm_all = pd.DataFrame([])
for d in dates:
    d_range = pd.date_range(d, d)
    data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                            start_time=start_time, end_time=end_time)
    sm = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
    sm_all = pd.concat([sm_all, sm], axis=0)

 
    if add_trades:
        col_list=['bid', 'ask', 'volume', 'broker_id']
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_s,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        tm = spread_class.add_trades(data_dict, trade_dict, coeff_list, mm_bool)
        print(tm.shape)
        tm_all = pd.concat([tm_all, tm], axis=0)

 
sm_all['mid'] = 0.5 * (sm_all['bid'] + sm_all['ask'])
if len(sm_all) >0:
    ohlc_df = sm_all['mid'].resample('1H').ohlc()
    if len(market) == 2:
        file_name = f"{market[0]}{tenor[0]}{tn1_list[0]}x{market[1]}{tenor[1]}{tn1_list[1]}"
    else:
        file_name = f"{market[0]}{tenor[0]}{tn1_list[0]}"
    ohlc_df.ffill().to_csv(f'C:\\Users\\david\\data_factory\\{file_name}.csv')