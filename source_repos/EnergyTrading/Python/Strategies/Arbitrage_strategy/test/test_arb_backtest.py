# -*- coding: utf-8 -*-
"""
Created on Wed Jan 22 09:52:05 2025

@author: Marek
"""

from datetime import datetime, time
from Database.TPData import TPData
from SynthSpread.spreadviewer_class import SpreadSingle
import pandas as pd
import matplotlib.pyplot as plt
from Strategies.Arbitrage_strategy.backtest_class import BacktestArb
from Strategies.Arbitrage_strategy.strategy_class import StrategyArb
from Strategies.Market_making.strategy_class import VolumeClass
from OrderBook.OrderBook import OrderBookSnaps
from Utilities.excel_loaders import conn_out_xload

l_path = '//192.168.10.91/data/Data/orderbooks/base/'
# l_path = '/Volumes/data/Data/orderbooks/base/'


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


def venue_code_dict(venue):
    my_dict = {}
    my_dict['EEX'] = 1441
    my_dict['GFI'] = 2
    my_dict['TFS'] = 7
    my_dict['42FS'] = 8
    my_dict['ICAP'] = 6
    my_dict['EEX7'] = 1441
    my_dict['SPEC'] = 5
    my_dict['GRFN'] = 3
    my_dict['BGC'] = 10
    return my_dict[venue]


n_s = 2
mkt = 'de'
tenor = 'y'
tn1 = 1
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2025, 6, 1)
end_date = datetime(2025, 6, 26)

if not tn2_list:
    tn_list = [str(t1) for t1 in [tn1]]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip([tn1], tn2_list)]

dates_out = conn_out_xload()
dates = pd.date_range(start_date, end_date, freq='B')

spread_class = SpreadSingle([mkt], [tenor], [tn1], [], venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

start_time = time(9, 0, 0, 0)
end_time = time(17, 0, 0, 0)

data_class = TPData()

# brk_ids = [1441, 7, 2, 5, 8, 3, 10]
#
brk_ids = [venue_code_dict(ven) for ven in ['EEX', 'ICAP', 'BGC', 'SPEC', 'GRFN', 'GFI']]
# brk_ids = [venue_code_dict(ven) for ven in ['EEX', 'TFS', '42FS']]
# brk_ids = [1441]
agg_dict = {'price': 'first', 'volume': 'first', 'action': 'first',
            'broker_id': 'first', 'count': 'first'}

# Classes
method = 'fix'
min_lvl_cover = 0.1
instr = mkt + tenor + tn_list[0]
price_tick = .01
broker_list = brk_ids
vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestArb(vol_class)
strategy_class = StrategyArb(mkt, instr, price_tick, broker_list,
                             time_exe=.1, time_del=.05, min_lvl_cover=min_lvl_cover)
param_dict = {'mkt_depth_check': True, 'cons_level': 0.05}
# param_dict = {}
strategy_class.update_params(param_dict)

# param_dict = {'margin': .09, 'min_margin': 0.07, 'max_margin': 0.15}

# strategy_class = StrategyArb(mkt, instr, price_tick, broker_list,
#                              time_exe=.2, time_del=.02)

# Load Data
data_dict = {}
pnl_dict = {}
pnl_ser = pd.Series([])
for d, p_date in zip(dates, product_date1[0]):
    if d in dates_out:
        continue
    p_d = p_date
    bT = datetime.combine(d, start_time)
    eT = datetime.combine(d, end_time)
    # Trades
    data_class.create_connection('OracleSQL')
    try:
        df_tr = data_class.get_trades(mkt, tenor, venue_list, p_d, bT, eT, prod)
    except AttributeError:
        continue
    # Group trades
    df_tr = group_trades(df_tr, agg_dict).between_time(start_time, end_time)
    # Orders
    LoB_dict, time_list = load_ob(mkt, tenor, bT, p_d, bT, eT)
    df_data_aux = backtest_class.merge_data_backtest(LoB_dict, df_tr, strategy_class, adj_action=True)
    
    try:
        data_dict[instr] = pd.concat([data_dict[instr], df_data_aux])
    except(KeyError):
        data_dict[instr] = df_data_aux
    # data_dict[instr] = backtest_class.merge_data_backtest(LoB_dict, df_tr, strategy_class, adj_action=True)
    # strategy_class.reset()
    # strategy_class.update_params(param_dict)
    # xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)

    # xd = strategy_class.stats_dict
    # if pnl_ser.empty:
    #     pnl_ser = xx
    #     pnl_dict = xd
    # else:
    #     pnl_start = pnl_ser.iloc[-1]
    #     pnl_ser = pd.concat([pnl_ser, xx + pnl_start])
    #     {k: v.extend(xd[k]) for k, v in pnl_dict.items()}


# param_dict = {'margin': .07, 'min_margin': 0.07, 'max_margin': 0.15}

# strategy_class = StrategyArb(mkt, instr, price_tick, broker_list,
#                              time_exe=.10, time_del=.02)
# strategy_class.update_params(param_dict)
# xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)

# xd = strategy_class.stats_dict

mrg_list = [0.07, 0.08, 0.09]
time_exe_list = [0.05, 0.06, 0.10, 0.15, 0.25]
xx_dict = {t: {} for t in time_exe_list}

for t_e in time_exe_list:
    plt.figure()
    for mrg in mrg_list:
        param_dict.update({'margin': mrg, 'min_margin': 0.07, 'max_margin': 0.25,
                           'cons_level': 0.10, 'mkt_depth_check': True, 'stop_loss': 0.08})
        param_dict.pop('cons_level')
        # param_dict = {'margin': mrg, 'min_margin': 0.07, 'max_margin': 0.15}
        
        strategy_class = StrategyArb(mkt, instr, price_tick, broker_list,
                                     time_exe=t_e, time_del=.02, min_lvl_cover=min_lvl_cover)
        strategy_class.update_params(param_dict)
        xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)
        xx.name = str(mrg)
        xx_dict[t_e][mrg] = xx.iloc[-1]
        xx.plot()

